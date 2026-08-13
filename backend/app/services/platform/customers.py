"""Customer registration and profile management."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.permissions import Role
from app.core.security import hash_password, verify_password
from app.models.platform import AiCreditAccount, Customer, PlatformAuditLog
from app.models.user import User
from app.schemas.platform import (
    CustomerRegisterRequest,
    CustomerResponse,
    CustomerVerifyEmailRequest,
)


class CustomerService:
    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session
        self._pending_codes: dict[str, tuple[str, datetime]] = {}

    async def register(self, body: CustomerRegisterRequest) -> tuple[CustomerResponse, str]:
        email = body.email.lower().strip()
        existing = await self._session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise ConflictError("An account with this email already exists.")

        username = self._username_from_email(email)
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(body.password),
            full_name=body.full_name.strip(),
            is_active=True,
            is_superuser=False,
            roles=[Role.CUSTOMER.value],
        )
        self._session.add(user)
        await self._session.flush()

        customer = Customer(
            user_id=user.id,
            email=email,
            full_name=body.full_name.strip(),
            phone=body.phone,
            company=body.company,
            email_verified=False,
        )
        self._session.add(customer)
        await self._session.flush()

        credits = AiCreditAccount(customer_id=customer.id, credits_remaining=0, total_allocated=0)
        self._session.add(credits)
        self._session.add(
            PlatformAuditLog(
                customer_id=customer.id,
                actor_id=user.id,
                action="customer.register",
                target_type="customer",
                target_id=str(customer.id),
                result="success",
            )
        )

        code = f"{secrets.randbelow(1_000_000):06d}"
        token = self._sign_verify_token(customer.id, code)
        # Dev/ops: return token so UI can verify without SMTP. SMTP send is best-effort.
        await self._try_send_verify_email(email, code)
        return CustomerResponse.model_validate(customer), token

    async def verify_email(self, body: CustomerVerifyEmailRequest) -> CustomerResponse:
        customer_id, code = self._parse_verify_token(body.token)
        if body.code.strip() != code:
            raise AuthenticationError("Invalid verification code.")
        customer = await self.get_by_id(customer_id)
        customer.email_verified = True
        await self._session.flush()
        return CustomerResponse.model_validate(customer)

    async def get_by_user_id(self, user_id: UUID) -> Customer | None:
        result = await self._session.execute(select(Customer).where(Customer.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, customer_id: UUID) -> Customer:
        result = await self._session.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            raise NotFoundError("Customer not found.")
        return customer

    async def require_for_user(self, user_id: UUID) -> Customer:
        customer = await self.get_by_user_id(user_id)
        if customer is None:
            raise NotFoundError("No customer profile for this account.")
        return customer

    async def authenticate_password(self, email: str, password: str) -> tuple[User, Customer]:
        identity = email.lower().strip()
        result = await self._session.execute(select(User).where(User.email == identity, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials.")
        if Role.CUSTOMER.value not in (user.roles or []) and not user.is_superuser:
            # Staff can still have a customer profile later; for portal login require customer role
            customer = await self.get_by_user_id(user.id)
            if customer is None:
                raise AuthenticationError("This login is for IFNOTUS customer accounts.")
        customer = await self.require_for_user(user.id)
        user.last_login_at = datetime.now(UTC)
        return user, customer

    def _username_from_email(self, email: str) -> str:
        local = re.sub(r"[^a-z0-9._-]+", "", email.split("@", 1)[0].lower())[:40] or "customer"
        suffix = secrets.token_hex(3)
        return f"{local}_{suffix}"

    def _sign_verify_token(self, customer_id: UUID, code: str) -> str:
        exp = int((datetime.now(UTC) + timedelta(hours=24)).timestamp())
        payload = f"{customer_id}:{code}:{exp}"
        sig = hmac.new(
            self._settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        return f"{payload}:{sig}"

    def _parse_verify_token(self, token: str) -> tuple[UUID, str]:
        parts = token.split(":")
        if len(parts) != 4:
            raise AuthenticationError("Invalid verification token.")
        customer_id_s, code, exp_s, sig = parts
        payload = f"{customer_id_s}:{code}:{exp_s}"
        expected = hmac.new(
            self._settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        if not hmac.compare_digest(expected, sig):
            raise AuthenticationError("Invalid verification token.")
        if int(exp_s) < int(datetime.now(UTC).timestamp()):
            raise AuthenticationError("Verification token expired.")
        return UUID(customer_id_s), code

    async def _try_send_verify_email(self, email: str, code: str) -> None:
        if not self._settings.smtp_host:
            return
        # Optional SMTP — failure must not block registration
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = "Verify your IFNOTUS account"
            msg["From"] = self._settings.smtp_from or "noreply@ifnotus.space"
            msg["To"] = email
            msg.set_content(f"Your IFNOTUS verification code is: {code}\n\nValid for 24 hours.")
            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as smtp:
                if self._settings.smtp_use_tls:
                    smtp.starttls()
                if self._settings.smtp_username:
                    smtp.login(self._settings.smtp_username, self._settings.smtp_password or "")
                smtp.send_message(msg)
        except Exception:
            return
