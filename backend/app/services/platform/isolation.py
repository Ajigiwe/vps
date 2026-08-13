"""Customer environment isolation — Docker when available, filesystem fallback."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class IsolationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def docker_available(self) -> bool:
        return bool(shutil.which("docker"))

    def preferred_mode(self) -> str:
        mode = (self._settings.customer_isolation_mode or "docker").lower()
        if mode == "docker" and not self.docker_available:
            return "filesystem"
        return mode if mode in {"docker", "filesystem"} else "filesystem"

    def allocate_port(self, environment_suffix: str) -> int:
        hex_only = "".join(ch for ch in environment_suffix.lower() if ch in "0123456789abcdef")
        n = int((hex_only[-4:] or "0"), 16) % 2000
        return 18000 + n

    def start_container(
        self,
        *,
        env_id: str,
        document_root: str,
        cpu: int,
        ram_gb: int,
        port: int,
    ) -> str | None:
        if not self.docker_available:
            return None
        name = f"ifnotus-env-{env_id[:12]}"
        Path(document_root).mkdir(parents=True, exist_ok=True)
        # Replace existing container with same name
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--restart",
            "unless-stopped",
            "--cpus",
            str(max(cpu, 1)),
            "--memory",
            f"{max(ram_gb, 1)}g",
            "-p",
            f"127.0.0.1:{port}:80",
            "-v",
            f"{document_root}:/usr/share/nginx/html:ro",
            "nginx:alpine",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
        if result.returncode != 0:
            logger.warning("docker_start_failed", name=name, error=(result.stderr or result.stdout)[:400])
            return None
        container_id = (result.stdout or "").strip() or name
        logger.info("docker_started", name=name, port=port, id=container_id[:16])
        return container_id

    def resize_container(self, container_id: str | None, *, cpu: int, ram_gb: int) -> None:
        if not container_id or not self.docker_available:
            return
        subprocess.run(
            [
                "docker",
                "update",
                "--cpus",
                str(max(cpu, 1)),
                "--memory",
                f"{max(ram_gb, 1)}g",
                container_id,
            ],
            capture_output=True,
            check=False,
        )

    def stop_container(self, container_id: str | None, *, env_id: str | None = None) -> None:
        if not self.docker_available:
            return
        names: list[str] = []
        if container_id:
            names.append(container_id)
        if env_id:
            names.append(f"ifnotus-env-{env_id[:12]}")
        for name in names:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
