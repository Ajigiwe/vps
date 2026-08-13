"""One-time login challenges for untrusted admin IPs."""

from __future__ import annotations

import json
import secrets
import string
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PATH = Path("/srv/apps/podium/backend/.podium/state/login-challenges.json")
FALLBACK_PATH = Path(".podium/state/login-challenges.json")
CHALLENGE_TTL_MINUTES = 15
CODE_LENGTH = 6
_lock = Lock()


@dataclass
class LoginChallenge:
    challenge_id: str
    code: str
    ip_address: str
    user_id: str
    username_or_email: str
    device_fingerprint: str | None
    user_agent: str | None
    created_at: str
    expires_at: str
    consumed: bool = False

    def is_expired(self) -> bool:
        try:
            return datetime.fromisoformat(self.expires_at) <= datetime.now(UTC)
        except ValueError:
            return True


def _path() -> Path:
    if DEFAULT_PATH.parent.exists() or Path("/srv/apps/podium/backend").exists():
        DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        return DEFAULT_PATH
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    return FALLBACK_PATH


def _load() -> dict[str, LoginChallenge]:
    path = _path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, LoginChallenge] = {}
    for item in raw.get("challenges", []):
        try:
            ch = LoginChallenge(**item)
        except TypeError:
            continue
        out[ch.challenge_id] = ch
    return out


def _save(challenges: dict[str, LoginChallenge]) -> None:
    path = _path()
    # Drop expired / consumed older than 24h.
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    kept: list[dict] = []
    for ch in challenges.values():
        try:
            created = datetime.fromisoformat(ch.created_at)
        except ValueError:
            continue
        if ch.consumed and created < cutoff:
            continue
        if ch.is_expired() and created < cutoff:
            continue
        kept.append(asdict(ch))
    path.write_text(json.dumps({"challenges": kept}, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _new_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"IF-{body}"


def _new_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(CODE_LENGTH))


def create_challenge(
    *,
    ip_address: str,
    user_id: str,
    username_or_email: str,
    device_fingerprint: str | None,
    user_agent: str | None,
) -> LoginChallenge:
    with _lock:
        challenges = _load()
        # Replace any open challenge for same user+ip.
        for existing in list(challenges.values()):
            if (
                not existing.consumed
                and not existing.is_expired()
                and existing.ip_address == ip_address
                and existing.user_id == user_id
            ):
                existing.consumed = True
        now = datetime.now(UTC)
        ch = LoginChallenge(
            challenge_id=_new_id(),
            code=_new_code(),
            ip_address=ip_address,
            user_id=user_id,
            username_or_email=username_or_email,
            device_fingerprint=device_fingerprint,
            user_agent=(user_agent or "")[:512] or None,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=CHALLENGE_TTL_MINUTES)).isoformat(),
            consumed=False,
        )
        challenges[ch.challenge_id] = ch
        _save(challenges)
        logger.info(
            "login_challenge_created",
            challenge_id=ch.challenge_id,
            ip=ip_address,
            user=username_or_email,
        )
        return ch


def list_pending() -> list[LoginChallenge]:
    with _lock:
        challenges = _load()
        pending = [
            ch
            for ch in challenges.values()
            if not ch.consumed and not ch.is_expired()
        ]
        pending.sort(key=lambda c: c.created_at, reverse=True)
        return pending


def consume_challenge(challenge_id: str, code: str) -> LoginChallenge | None:
    with _lock:
        challenges = _load()
        ch = challenges.get(challenge_id.strip().upper())
        if ch is None:
            # also try as-is
            ch = challenges.get(challenge_id.strip())
        if ch is None or ch.consumed or ch.is_expired():
            return None
        if ch.code != code.strip():
            return None
        ch.consumed = True
        challenges[ch.challenge_id] = ch
        _save(challenges)
        return ch


def approve_challenge(challenge_id: str) -> LoginChallenge | None:
    """Mark challenge consumed after CLI approval (code already verified offline)."""
    with _lock:
        challenges = _load()
        ch = challenges.get(challenge_id.strip().upper()) or challenges.get(challenge_id.strip())
        if ch is None or ch.consumed or ch.is_expired():
            return None
        ch.consumed = True
        challenges[ch.challenge_id] = ch
        _save(challenges)
        return ch


def get_challenge(challenge_id: str) -> LoginChallenge | None:
    with _lock:
        challenges = _load()
        return challenges.get(challenge_id.strip().upper()) or challenges.get(challenge_id.strip())
