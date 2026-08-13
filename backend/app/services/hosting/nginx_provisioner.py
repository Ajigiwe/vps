"""Provision nginx vhosts for managed domains (cPanel-style)."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import AppException
from app.schemas.operations import OperationResult
from app.services.hosting.nginx_sites import NginxSiteManager
from app.services.monitoring.subprocess_util import resolve_binary, run_command

MANAGED_MARKER = "# managed-by-Podium: domain-vhost"


class DomainNginxProvisioner:
    """Write / enable / remove nginx site configs for domains."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._available = Path(settings.nginx_sites_available)
        self._enabled = Path(settings.nginx_sites_enabled)
        self._sites = NginxSiteManager(settings)

    def site_name(self, hostname: str) -> str:
        # Match existing style on this host: full hostname as filename
        safe = re.sub(r"[^a-z0-9._-]+", "-", hostname.lower()).strip("-.")
        return safe or "site"

    def site_paths(self, hostname: str) -> tuple[Path, Path]:
        name = self.site_name(hostname)
        return self._available / name, self._enabled / name

    def ensure_document_root(self, path: str) -> Path:
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        index = root / "index.html"
        if not index.exists():
            index.write_text(
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>{root.name}</title></head><body>"
                "<h1>It works</h1><p>Provisioned by Podium.</p></body></html>\n",
                encoding="utf-8",
            )
        return root

    def render_config(
        self,
        *,
        hostname: str,
        document_root: str | None,
        proxy_port: int | None,
        force_https: bool,
        redirect_url: str | None,
        aliases: list[str] | None = None,
        ssl_certificate: str | None = None,
        ssl_certificate_key: str | None = None,
        path_redirects: list[dict] | None = None,
    ) -> str:
        names = [hostname] + [a for a in (aliases or []) if a and a != hostname]
        names_line = " ".join(dict.fromkeys(names))
        root = document_root or f"/var/www/{hostname}"
        cert = ssl_certificate
        key = ssl_certificate_key
        if not cert or not key:
            le = Path(f"/etc/letsencrypt/live/{hostname}")
            if (le / "fullchain.pem").exists() and (le / "privkey.pem").exists():
                cert = str(le / "fullchain.pem")
                key = str(le / "privkey.pem")

        lines: list[str] = [
            MANAGED_MARKER,
            f"# domain={hostname}",
            "",
        ]

        # HTTP server
        lines += [
            "server {",
            "    listen 80;",
            "    listen [::]:80;",
            f"    server_name {names_line};",
        ]
        if force_https and cert and key:
            lines += [
                "    location ^~ /.well-known/acme-challenge/ {",
                f"        root {root};",
                "        default_type text/plain;",
                "    }",
                "    location / {",
                "        return 301 https://$host$request_uri;",
                "    }",
                "}",
                "",
            ]
        else:
            lines += self._location_block(
                root=root,
                proxy_port=proxy_port,
                redirect_url=redirect_url,
                path_redirects=path_redirects or [],
            )
            lines += ["}", ""]

        # HTTPS server when cert present
        if cert and key:
            lines += [
                "server {",
                "    listen 443 ssl;",
                "    listen [::]:443 ssl;",
                f"    server_name {names_line};",
                f"    ssl_certificate {cert};",
                f"    ssl_certificate_key {key};",
            ]
            if Path("/etc/letsencrypt/options-ssl-nginx.conf").exists():
                lines.append("    include /etc/letsencrypt/options-ssl-nginx.conf;")
            if Path("/etc/letsencrypt/ssl-dhparams.pem").exists():
                lines.append("    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;")
            lines += self._location_block(
                root=root,
                proxy_port=proxy_port,
                redirect_url=redirect_url,
                path_redirects=path_redirects or [],
            )
            lines += ["}", ""]

        return "\n".join(lines)

    def _webmail_locations(self) -> list[str]:
        """Serve Roundcube at /mail on every managed domain (before catch-all proxy/redirect)."""
        public = Path(self._settings.roundcube_public_html)
        sock = Path(self._settings.php_fpm_socket)
        if not public.is_dir():
            return [
                "    # Roundcube webmail skipped — document root missing",
                f"    # expected: {public}",
            ]
        php_sock = str(sock) if sock.exists() else "/run/php/php8.3-fpm.sock"
        root = str(public)
        return [
            "    # Roundcube webmail (Podium) — https://{domain}/mail/",
            "    location = /mail {",
            "        return 302 /mail/;",
            "    }",
            "    location ~ ^/mail/(.+\\.php)$ {",
            "        include fastcgi_params;",
            f"        fastcgi_param SCRIPT_FILENAME {root}/$1;",
            f"        fastcgi_pass unix:{php_sock};",
            "    }",
            "    location = /mail/ {",
            "        rewrite ^ /mail/index.php last;",
            "    }",
            "    location /mail/ {",
            f"        alias {root}/;",
            "    }",
        ]

    def _location_block(
        self,
        *,
        root: str,
        proxy_port: int | None,
        redirect_url: str | None,
        path_redirects: list[dict],
    ) -> list[str]:
        lines: list[str] = [f"    root {root};", "    index index.html index.htm index.php;"]
        # Webmail must win over whole-site redirect and app proxy_pass.
        lines += self._webmail_locations()
        for redir in path_redirects:
            if not redir.get("enabled", True):
                continue
            source = str(redir.get("source_path") or "/").strip() or "/"
            target = str(redir.get("target_url") or "").strip()
            code = int(redir.get("status_code") or 301)
            if not target:
                continue
            if source == "/":
                # whole-site path redirect handled below via redirect_url preference
                continue
            lines += [
                f"    location = {source} {{",
                f"        return {code} {target};",
                "    }",
            ]
            # also prefix match for trailing paths when source ends without file
            if not Path(source).suffix:
                lines += [
                    f"    location {source.rstrip('/')}/ {{",
                    f"        return {code} {target};",
                    "    }",
                ]

        if redirect_url:
            code = 301
            lines += [
                "    location / {",
                f"        return {code} {redirect_url};",
                "    }",
            ]
            return lines

        if proxy_port:
            lines += [
                "    location / {",
                f"        proxy_pass http://127.0.0.1:{proxy_port};",
                "        proxy_http_version 1.1;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto $scheme;",
                "        proxy_set_header Upgrade $http_upgrade;",
                "        proxy_set_header Connection $connection_upgrade;",
                "    }",
            ]
            # map for upgrade may not exist — keep Connection close-safe alternative
            # Use simpler connection header if map missing
            return [
                line.replace("proxy_set_header Connection $connection_upgrade;", 'proxy_set_header Connection "";')
                if "connection_upgrade" in line
                else line
                for line in lines
            ]

        lines += [
            "    location / {",
            "        try_files $uri $uri/ /index.html;",
            "    }",
        ]
        # Optional PHP if FPM socket exists
        if Path("/run/php/php-fpm.sock").exists() and Path("/etc/nginx/snippets/fastcgi-php.conf").exists():
            lines += [
                "    location ~ \\.php$ {",
                "        include snippets/fastcgi-php.conf;",
                "        fastcgi_pass unix:/run/php/php-fpm.sock;",
                "    }",
            ]
        return lines

    def inject_webmail_into_config(self, conf: str) -> str:
        """Insert Roundcube /mail locations before catch-all `location /` (never inside if{})."""
        if "location = /mail" in conf or "Roundcube webmail (Podium)" in conf:
            return conf
        block_lines = self._webmail_locations()
        if not block_lines or "skipped" in (block_lines[0] if block_lines else ""):
            return conf
        block = "\n".join(block_lines) + "\n"
        # Only match catch-all location / — avoids Certbot if ($host) blocks.
        updated = re.sub(r"(^[ \t]*location / \{)", block + r"\1", conf, flags=re.MULTILINE)
        if updated != conf:
            return updated
        # Parking / redirect HTTPS servers: insert after ssl_certificate_key once.
        if "ssl_certificate_key" in conf:
            updated = re.sub(
                r"(ssl_certificate_key\s+[^;]+;\s*(?:#[^\n]*)?\n)",
                r"\1" + block,
                conf,
                count=1,
            )
            if updated != conf:
                return updated
        return conf

    async def ensure_webmail_on_all_sites(self) -> OperationResult:
        """Add /mail webmail to every nginx site that does not already have it."""
        if not self._available.is_dir():
            return OperationResult(success=False, message="nginx sites-available missing")
        changed: list[str] = []
        skipped: list[str] = []
        enabled_names = set()
        if self._enabled.is_dir():
            for link in self._enabled.iterdir():
                enabled_names.add(link.name)

        for path in sorted(self._available.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            name = path.name
            # Never touch backups / package leftovers / disabled drafts
            if ".bak" in name or name.endswith((".tmp", ".dpkg-old", ".dpkg-dist", ".swp")):
                continue
            if name.endswith(".pre-webmail"):
                continue
            # Prefer enabled sites; also allow managed available sites not yet linked
            if enabled_names and name not in enabled_names:
                skipped.append(name)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            updated = self.inject_webmail_into_config(text)
            if updated == text:
                skipped.append(name)
                continue
            bak = path.with_name(f"{name}.bak-Podium-mail")
            try:
                if not bak.exists():
                    bak.write_text(text, encoding="utf-8")
                path.write_text(updated, encoding="utf-8")
                changed.append(name)
            except OSError as exc:
                return OperationResult(
                    success=False,
                    message=f"Failed writing {name}: {exc}",
                    details={"changed": changed, "skipped": skipped},
                )

        if not changed:
            return OperationResult(
                success=True,
                message="All nginx sites already expose /mail webmail.",
                details={"changed": changed, "skipped": skipped},
            )
        reload = await self._sites.reload()
        if not reload.success:
            # Reload failed — try to revert changed files from bak
            for name in changed:
                bak = self._available / f"{name}.bak-Podium-mail"
                site = self._available / name
                if bak.exists():
                    try:
                        site.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
                    except OSError:
                        pass
            return OperationResult(
                success=False,
                message=reload.message,
                details={"changed": changed, "skipped": skipped, "reverted": True},
            )
        return OperationResult(
            success=True,
            message=f"Added /mail webmail to {len(changed)} nginx site(s).",
            details={"changed": changed, "skipped": skipped},
        )

    async def provision(
        self,
        *,
        hostname: str,
        document_root: str | None,
        proxy_port: int | None,
        force_https: bool = False,
        redirect_url: str | None = None,
        aliases: list[str] | None = None,
        ssl_certificate: str | None = None,
        enabled: bool = True,
        create_docroot: bool = True,
        path_redirects: list[dict] | None = None,
    ) -> OperationResult:
        root = document_root or f"/var/www/{hostname}"
        if create_docroot and not redirect_url:
            try:
                self.ensure_document_root(root)
            except OSError as exc:
                raise AppException(f"Could not create document root: {exc}", code="docroot_failed") from exc

        available, enabled_path = self.site_paths(hostname)
        self._available.mkdir(parents=True, exist_ok=True)
        self._enabled.mkdir(parents=True, exist_ok=True)

        # Preserve existing SSL paths from prior config if present
        if available.exists() and not ssl_certificate:
            try:
                old = available.read_text(encoding="utf-8", errors="replace")
                m_cert = re.search(r"ssl_certificate\s+([^;]+);", old)
                m_key = re.search(r"ssl_certificate_key\s+([^;]+);", old)
                if m_cert and m_key:
                    ssl_certificate = m_cert.group(1).strip()
                    ssl_key = m_key.group(1).strip()
                else:
                    ssl_key = None
            except OSError:
                ssl_key = None
        else:
            ssl_key = None
            if ssl_certificate:
                # derive key path conventionally
                p = Path(ssl_certificate)
                ssl_key = str(p.parent / "privkey.pem") if p.name == "fullchain.pem" else None

        content = self.render_config(
            hostname=hostname,
            document_root=root,
            proxy_port=proxy_port,
            force_https=force_https,
            redirect_url=redirect_url,
            aliases=aliases,
            ssl_certificate=ssl_certificate,
            ssl_certificate_key=ssl_key if ssl_certificate else None,
            path_redirects=path_redirects,
        )
        tmp = available.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(available)

        try:
            if enabled:
                if enabled_path.exists() or enabled_path.is_symlink():
                    enabled_path.unlink()
                enabled_path.symlink_to(available)
            else:
                if enabled_path.is_symlink() or enabled_path.exists():
                    enabled_path.unlink()
        except OSError as exc:
            raise AppException(f"Failed to enable nginx site: {exc}", code="nginx_enable_failed") from exc

        reload = await self._sites.reload()
        if not reload.success:
            return OperationResult(
                success=False,
                message=reload.message,
                details={"site": str(available), "enabled": enabled},
            )
        return OperationResult(
            success=True,
            message=f"Nginx site provisioned for {hostname}.",
            details={
                "site": str(available),
                "enabled_path": str(enabled_path),
                "document_root": root,
                "enabled": enabled,
            },
        )

    async def set_enabled(self, hostname: str, enabled: bool) -> OperationResult:
        available, enabled_path = self.site_paths(hostname)
        if not available.exists():
            return OperationResult(success=False, message=f"No nginx site for {hostname}. Provision first.")
        try:
            if enabled:
                if enabled_path.exists() or enabled_path.is_symlink():
                    enabled_path.unlink()
                enabled_path.symlink_to(available)
            else:
                if enabled_path.exists() or enabled_path.is_symlink():
                    enabled_path.unlink()
        except OSError as exc:
            return OperationResult(success=False, message=str(exc))
        reload = await self._sites.reload()
        if not reload.success:
            return reload
        return OperationResult(
            success=True,
            message=f"Nginx site for {hostname} {'enabled' if enabled else 'disabled'}.",
        )

    async def remove(self, hostname: str, *, remove_files: bool = True) -> OperationResult:
        available, enabled_path = self.site_paths(hostname)
        try:
            if enabled_path.exists() or enabled_path.is_symlink():
                enabled_path.unlink()
            if remove_files and available.exists():
                # Only remove if Podium-managed
                head = available.read_text(encoding="utf-8", errors="replace")[:200]
                if MANAGED_MARKER in head:
                    available.unlink()
        except OSError as exc:
            return OperationResult(success=False, message=str(exc))
        reload = await self._sites.reload()
        return OperationResult(
            success=reload.success,
            message=f"Removed nginx site for {hostname}." if reload.success else reload.message,
        )
