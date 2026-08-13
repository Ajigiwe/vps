"""Domain registrar — Namecheap when configured, otherwise local stub."""

from __future__ import annotations

from decimal import Decimal
from xml.etree import ElementTree

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.platform.orders import DOMAIN_PRICES

logger = get_logger(__name__)


class DomainRegistrar:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.namecheap_api_user
            and self._settings.namecheap_api_key
            and self._settings.namecheap_client_ip
        )

    async def check(self, name: str, extension: str) -> dict:
        sld = name.lower().strip().replace(" ", "")
        tld = extension.lower().lstrip(".")
        domain = f"{sld}.{tld}"
        price = DOMAIN_PRICES.get(f".{tld}", Decimal("0"))
        reserved = {"Podium", "www", "mail", "ftp", "admin", "api", "csdttu", "examflow"}
        if sld in reserved or len(sld) < 3:
            return {
                "domain": domain,
                "available": False,
                "price_yearly": price,
                "currency": "GHS",
                "message": "Unavailable or reserved",
                "provider": "local",
            }

        if not self.enabled:
            return {
                "domain": domain,
                "available": True,
                "price_yearly": price,
                "currency": "GHS",
                "message": "Available (registrar API not configured — local check)",
                "provider": "stub",
            }

        try:
            available = await self._namecheap_available(sld, tld)
        except Exception as exc:  # noqa: BLE001
            logger.warning("namecheap_check_failed", domain=domain, error=str(exc))
            return {
                "domain": domain,
                "available": True,
                "price_yearly": price,
                "currency": "GHS",
                "message": f"Registrar lookup failed, treating as available: {exc}",
                "provider": "namecheap-error",
            }

        return {
            "domain": domain,
            "available": available,
            "price_yearly": price,
            "currency": "GHS",
            "message": "Available" if available else "Taken",
            "provider": "namecheap",
        }

    async def register(self, name: str, extension: str, years: int = 1) -> dict:
        check = await self.check(name, extension)
        if not check["available"]:
            return {**check, "registered": False, "message": check["message"]}
        if not self.enabled:
            return {
                **check,
                "registered": False,
                "message": "Namecheap API not configured. Point DNS to this server after you buy the domain.",
            }

        sld = name.lower().strip()
        tld = extension.lower().lstrip(".")
        params = self._auth_params()
        params.update(
            {
                "Command": "namecheap.domains.create",
                "DomainName": f"{sld}.{tld}",
                "Years": str(years),
            }
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._settings.namecheap_api_url, params=params)
        ok = "Status=\"OK\"" in resp.text or "Status='OK'" in resp.text
        return {
            "domain": f"{sld}.{tld}",
            "registered": ok,
            "provider": "namecheap",
            "message": "Registered" if ok else resp.text[:300],
        }

    async def _namecheap_available(self, sld: str, tld: str) -> bool:
        params = self._auth_params()
        params.update(
            {
                "Command": "namecheap.domains.check",
                "DomainList": f"{sld}.{tld}",
            }
        )
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(self._settings.namecheap_api_url, params=params)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.text)
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        for el in root.iter(f"{ns}DomainCheckResult"):
            avail = (el.attrib.get("Available") or "").lower()
            return avail == "true"
        # Fallback string parse
        return 'Available="true"' in resp.text or "Available='true'" in resp.text

    def _auth_params(self) -> dict[str, str]:
        return {
            "ApiUser": self._settings.namecheap_api_user or "",
            "ApiKey": self._settings.namecheap_api_key or "",
            "UserName": self._settings.namecheap_api_user or "",
            "ClientIp": self._settings.namecheap_client_ip or self._settings.server_public_ip or "",
        }
