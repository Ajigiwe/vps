"""Authentication service."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.permissions import Role, roles_have_permission
from app.core.security import TokenType, create_token_pair, decode_token, verify_password
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    VerifyDeviceRequest,
)
from app.services.access_control import (
    AccessContext,
    AccessControlService,
    IpBlockedError,
)
from app.services import auth_challenges


class AuthService:
    """Handles authentication and token lifecycle."""

    def __init__(
        self,
        settings: Settings,
        user_repository: UserRepository,
        access_control: AccessControlService | None = None,
    ) -> None:
        self._settings = settings
        self._users = user_repository
        self._access = access_control

    async def login(self, credentials: LoginRequest, ctx: AccessContext | None = None) -> LoginResponse:
        """Authenticate user; may require a one-time IP approval challenge."""
        identity = credentials.email.strip()
        fingerprint = credentials.device_fingerprint or (ctx.device_fingerprint if ctx else None)
        access_ctx = ctx or AccessContext(ip_address="unknown")
        if fingerprint and not access_ctx.device_fingerprint:
            access_ctx = AccessContext(
                ip_address=access_ctx.ip_address,
                user_agent=access_ctx.user_agent,
                device_fingerprint=fingerprint,
                request_id=access_ctx.request_id,
                source=access_ctx.source,
            )

        if self._access:
            # Login is reachable from any IP so a successful auth can trust the
            # caller. Brute-force blacklist still applies.
            try:
                await self._access.assert_ip_allowed(access_ctx)
            except IpBlockedError:
                await self._access.record_login_failure(
                    access_ctx,
                    username_or_email=identity,
                    reason="ip_blocked",
                )
                raise

        user = await self._users.get_by_email(identity)
        if user is None:
            user = await self._users.get_by_username(identity)

        if user is None:
            if self._access:
                await self._access.record_login_failure(
                    access_ctx,
                    username_or_email=identity,
                    reason="invalid_credentials",
                )
            raise AuthenticationError("Invalid credentials.")

        if not user.is_active:
            if self._access:
                await self._access.record_login_failure(
                    access_ctx,
                    username_or_email=identity,
                    reason="inactive",
                    user_id=user.id,
                )
            raise AuthenticationError("Invalid credentials.")

        if not verify_password(credentials.password, user.hashed_password):
            if self._access:
                await self._access.record_login_failure(
                    access_ctx,
                    username_or_email=identity,
                    reason="invalid_credentials",
                    user_id=user.id,
                )
            raise AuthenticationError("Invalid credentials.")

        needs_challenge = False
        if self._access and self._settings.admin_lockdown_enabled:
            trusted = await self._access._is_trusted_admin_ip(access_ctx.ip_address)
            needs_challenge = not trusted

        if needs_challenge:
            challenge = auth_challenges.create_challenge(
                ip_address=access_ctx.ip_address,
                user_id=str(user.id),
                username_or_email=identity,
                device_fingerprint=access_ctx.device_fingerprint,
                user_agent=access_ctx.user_agent,
            )
            if self._access:
                await self._access._record(
                    access_ctx,
                    event_type="login_challenge",
                    success=False,
                    failure_reason="challenge_required",
                    username_or_email=identity,
                    user_id=user.id,
                )
            return LoginResponse(
                status="challenge_required",
                challenge_id=challenge.challenge_id,
                ip_address=access_ctx.ip_address,
                message=(
                    f"New IP {access_ctx.ip_address} needs approval. "
                    f"On the server run: podium-unlock pending — then enter the code here. "
                    f"Challenge ID: {challenge.challenge_id}"
                ),
            )

        return await self._issue_session(user, access_ctx, identity=identity)

    async def verify_device(
        self,
        body: VerifyDeviceRequest,
        ctx: AccessContext | None = None,
    ) -> LoginResponse:
        """Complete a pending IP challenge and issue tokens."""
        access_ctx = ctx or AccessContext(ip_address="unknown")
        if body.device_fingerprint and not access_ctx.device_fingerprint:
            access_ctx = AccessContext(
                ip_address=access_ctx.ip_address,
                user_agent=access_ctx.user_agent,
                device_fingerprint=body.device_fingerprint,
                request_id=access_ctx.request_id,
                source=access_ctx.source,
            )

        if self._access:
            try:
                await self._access.assert_ip_allowed(access_ctx)
            except IpBlockedError:
                raise AuthenticationError("This IP is blacklisted.") from None

        challenge = auth_challenges.consume_challenge(body.challenge_id, body.code)
        if challenge is None:
            raise AuthenticationError("Invalid or expired approval code.")

        if challenge.ip_address != access_ctx.ip_address and access_ctx.ip_address not in {
            "unknown",
            "127.0.0.1",
            "::1",
        }:
            # Soft check: prefer same IP, but allow if proxy changed slightly only when equal.
            raise AuthenticationError(
                f"Approval code is for IP {challenge.ip_address}, but this request is from "
                f"{access_ctx.ip_address}."
            )

        user = await self._users.get_by_id(UUID(challenge.user_id))
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive.")

        return await self._issue_session(
            user,
            access_ctx,
            identity=challenge.username_or_email,
            trust_ip=challenge.ip_address,
        )

    async def _issue_session(
        self,
        user,
        access_ctx: AccessContext,
        *,
        identity: str,
        trust_ip: str | None = None,
    ) -> LoginResponse:
        user.last_login_at = datetime.now(UTC)
        await self._users.update(user)

        if self._access:
            # Trust the challenge IP (or current) before recording success.
            ip = trust_ip or access_ctx.ip_address
            await self._access.trust_authenticated_ip(ip, reason="login_success")
            await self._access.record_login_success(
                access_ctx,
                username_or_email=identity,
                user_id=user.id,
            )

        roles = user.get_roles()
        scopes = self._roles_to_scopes(roles)
        pair = create_token_pair(self._settings, subject=user.id, scopes=scopes)
        return LoginResponse(
            status="ok",
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
            ip_address=access_ctx.ip_address,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Issue new token pair from a valid refresh token."""
        payload = decode_token(self._settings, refresh_token)
        if payload.type != TokenType.REFRESH:
            raise AuthenticationError("Invalid token type.")

        user = await self._users.get_by_id(payload.sub)
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive.")

        scopes = self._roles_to_scopes(user.get_roles())
        pair = create_token_pair(self._settings, subject=user.id, scopes=scopes)

        return TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        )

    async def get_current_user(self, token: str) -> AuthenticatedUser:
        """Resolve authenticated user from access token."""
        payload = decode_token(self._settings, token)
        if payload.type != TokenType.ACCESS:
            raise AuthenticationError("Invalid token type.")

        user = await self._users.get_by_id(payload.sub)
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive.")

        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            username=user.username,
            roles=user.roles,
            is_superuser=user.is_superuser,
            scopes=payload.scopes,
        )

    def user_has_permission(self, user: AuthenticatedUser, permission: str) -> bool:
        if user.is_superuser:
            return True
        from app.core.permissions import Permission

        try:
            perm = Permission(permission)
        except ValueError:
            return False
        roles: list[Role] = []
        for role_str in user.roles:
            try:
                roles.append(Role(role_str))
            except ValueError:
                continue
        return roles_have_permission(roles, perm)

    async def confirm_password(self, user: AuthenticatedUser, password: str) -> None:
        db_user = await self._users.get_by_id(user.id)
        if db_user is None or not verify_password(password, db_user.hashed_password):
            raise AuthenticationError("Invalid password.")

    @staticmethod
    def _roles_to_scopes(roles: list[str]) -> list[str]:
        scopes: list[str] = []
        for role in roles:
            try:
                scopes.append(Role(role).value)
            except ValueError:
                continue
        return scopes
