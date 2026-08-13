"""Podium customer portal + product APIs."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.exceptions import AuthorizationError
from app.core.permissions import Role
from app.core.security import create_token_pair
from app.models.platform import Subscription
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.common import MessageResponse
from app.schemas.platform import (
    AiCreditAccountResponse,
    AiOperationCompleteRequest,
    AiOperationRequest,
    AiOperationResponse,
    AutoRenewRequest,
    CapacityNodeResponse,
    ChangePlanRequest,
    CreateOrderRequest,
    CreateOrderResponse,
    CustomerDashboardResponse,
    CustomerRegisterRequest,
    CustomerRegisterResponse,
    CustomerResponse,
    CustomerVerifyEmailRequest,
    DomainAvailabilityRequest,
    DomainAvailabilityResponse,
    EnvironmentResponse,
    NotificationResponse,
    OrderResponse,
    SubscriptionResponse,
    VerifyPaymentRequest,
)
from app.services.platform.billing import SubscriptionBillingService
from app.services.platform.credits import AiCreditService
from app.services.platform.customers import CustomerService
from app.services.platform.notifications import NotificationService
from app.services.platform.orders import OrderService
from app.services.platform.paystack import PaystackService
from app.services.platform.provisioning import ProvisioningEngine
from app.services.platform.registrar import DomainRegistrar
from app.services.platform.resources import ResourceManager

router = APIRouter()


def _require_customer_user(user) -> None:
    roles = set(user.roles or [])
    if user.is_superuser or Role.CUSTOMER.value in roles or Role.ADMIN.value in roles or Role.SUPERADMIN.value in roles:
        return
    raise AuthorizationError("Customer account required.")


@router.post("/register", response_model=CustomerRegisterResponse)
async def register_customer(
    body: CustomerRegisterRequest,
    session: DbSession,
    settings: SettingsDep,
) -> CustomerRegisterResponse:
    svc = CustomerService(settings, session)
    customer, token = await svc.register(body)
    return CustomerRegisterResponse(customer=customer, verification_token=token)


@router.post("/verify-email", response_model=CustomerResponse)
async def verify_email(
    body: CustomerVerifyEmailRequest,
    session: DbSession,
    settings: SettingsDep,
) -> CustomerResponse:
    return await CustomerService(settings, session).verify_email(body)


@router.post("/login", response_model=LoginResponse)
async def customer_login(
    body: LoginRequest,
    session: DbSession,
    settings: SettingsDep,
) -> LoginResponse:
    svc = CustomerService(settings, session)
    user, customer = await svc.authenticate_password(body.email, body.password)
    pair = create_token_pair(settings, subject=user.id)
    return LoginResponse(
        status="ok",
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
        message=f"Welcome to Podium, {customer.full_name}.",
    )


@router.get("/me", response_model=CustomerResponse)
async def customer_me(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> CustomerResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    return CustomerResponse.model_validate(customer)


@router.get("/dashboard", response_model=CustomerDashboardResponse)
async def customer_dashboard(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> CustomerDashboardResponse:
    _require_customer_user(user)
    customers = CustomerService(settings, session)
    customer = await customers.require_for_user(user.id)
    credits = await AiCreditService(session).get_account(customer.id)
    envs = await ProvisioningEngine(settings, session).list_environments(customer.id)
    subs_result = await session.execute(
        select(Subscription).where(Subscription.customer_id == customer.id).order_by(Subscription.created_at.desc())
    )
    subs = list(subs_result.scalars().all())
    notes = await NotificationService(session).list_for_customer(customer.id, unread_only=True)
    usage = await ResourceManager(session).active_subscription_usage(customer.id)
    return CustomerDashboardResponse(
        customer=CustomerResponse.model_validate(customer),
        credits=AiCreditAccountResponse(
            customer_id=credits.customer_id,
            credits_remaining=credits.credits_remaining,
            total_allocated=credits.total_allocated,
            lifetime_used=credits.lifetime_used,
        ),
        environments=[EnvironmentResponse.model_validate(e) for e in envs],
        subscriptions=[SubscriptionResponse.model_validate(s) for s in subs],
        unread_notifications=len(notes),
        usage=usage,
    )


@router.post("/orders", response_model=CreateOrderResponse)
async def create_order(
    body: CreateOrderRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> CreateOrderResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    data = await OrderService(settings, session).create_order(customer, body)
    return CreateOrderResponse(**data)


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> list[OrderResponse]:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    orders = await OrderService(settings, session).list_orders(customer.id)
    return [OrderResponse.model_validate(o) for o in orders]


@router.post("/orders/verify-payment", response_model=OrderResponse)
async def verify_payment(
    body: VerifyPaymentRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> OrderResponse:
    _require_customer_user(user)
    # Ensure the order belongs to this customer
    customer = await CustomerService(settings, session).require_for_user(user.id)
    order = await OrderService(settings, session).verify_and_activate(body.reference)
    if order.customer_id != customer.id and not user.is_superuser:
        raise AuthorizationError("This payment does not belong to your account.")
    return order


@router.post("/billing/webhook")
async def paystack_webhook(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
) -> MessageResponse:
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    paystack = PaystackService(settings)
    if not paystack.verify_webhook_signature(body, signature):
        raise AuthorizationError("Invalid Paystack signature.")
    import json

    event = json.loads(body.decode() or "{}")
    if event.get("event") == "charge.success":
        data = event.get("data") or {}
        reference = data.get("reference")
        if reference:
            await OrderService(settings, session).verify_and_activate(reference)
    return MessageResponse(message="ok")


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> list[EnvironmentResponse]:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    envs = await ProvisioningEngine(settings, session).list_environments(customer.id)
    return [EnvironmentResponse.model_validate(e) for e in envs]


@router.post("/environments/{environment_id}/suspend", response_model=EnvironmentResponse)
async def suspend_environment(
    environment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> EnvironmentResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    from app.services.platform.lifecycle import EnvironmentLifecycleService

    env = await EnvironmentLifecycleService(settings, session).suspend(customer.id, environment_id)
    return EnvironmentResponse.model_validate(env)


@router.post("/environments/{environment_id}/restore", response_model=EnvironmentResponse)
async def restore_environment(
    environment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> EnvironmentResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    from app.services.platform.lifecycle import EnvironmentLifecycleService

    env = await EnvironmentLifecycleService(settings, session).restore(customer.id, environment_id)
    return EnvironmentResponse.model_validate(env)


@router.post("/environments/{environment_id}/terminate", response_model=EnvironmentResponse)
async def terminate_environment(
    environment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> EnvironmentResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    from app.services.platform.lifecycle import EnvironmentLifecycleService

    env = await EnvironmentLifecycleService(settings, session).terminate(customer.id, environment_id)
    return EnvironmentResponse.model_validate(env)


@router.post("/environments/{environment_id}/backups")
async def create_backup(
    environment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
):
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    from app.services.platform.lifecycle import EnvironmentLifecycleService

    row = await EnvironmentLifecycleService(settings, session).create_backup(customer.id, environment_id)
    return {
        "id": str(row.id),
        "filename": row.filename,
        "status": row.status,
        "backup_type": row.backup_type,
    }


@router.get("/environments/{environment_id}/backups")
async def list_backups(
    environment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
):
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    from app.services.platform.lifecycle import EnvironmentLifecycleService

    rows = await EnvironmentLifecycleService(settings, session).list_backups(customer.id, environment_id)
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "status": r.status,
            "file_size": r.file_size,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/credits", response_model=AiCreditAccountResponse)
async def get_credits(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> AiCreditAccountResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    account = await AiCreditService(session).get_account(customer.id)
    return AiCreditAccountResponse(
        customer_id=account.customer_id,
        credits_remaining=account.credits_remaining,
        total_allocated=account.total_allocated,
        lifetime_used=account.lifetime_used,
    )


@router.post("/ai/operations", response_model=AiOperationResponse)
async def start_ai_operation(
    body: AiOperationRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> AiOperationResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    require_confirm = body.permission_level >= 3
    risk = body.risk_classification
    if body.permission_level == 4:
        risk = "critical"
    elif body.permission_level == 3:
        risk = "high"
    op = await AiCreditService(session).start_operation(
        customer_id=customer.id,
        environment_id=body.environment_id,
        operation_type=body.operation_type,
        permission_level=body.permission_level,
        request=body.request,
        risk=risk,
        require_confirm=require_confirm,
    )
    # Levels 1–2: mark complete with stub result (full agent wiring uses existing /ai)
    if not require_confirm:
        op = await AiCreditService(session).complete_operation(
            customer.id,
            op.id,
            success=True,
            result="Accepted. Use Podium AI chat for live troubleshooting within your environment.",
        )
    return AiOperationResponse.model_validate(op)


@router.post("/ai/operations/{operation_id}/confirm", response_model=AiOperationResponse)
async def confirm_ai_operation(
    operation_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> AiOperationResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    op = await AiCreditService(session).confirm_operation(customer.id, operation_id)
    op = await AiCreditService(session).complete_operation(
        customer.id,
        op.id,
        success=True,
        result="Confirmed and recorded. Apply the change via Podium AI propose/apply tools.",
    )
    return AiOperationResponse.model_validate(op)


@router.post("/ai/operations/{operation_id}/complete", response_model=AiOperationResponse)
async def complete_ai_operation(
    operation_id: UUID,
    body: AiOperationCompleteRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> AiOperationResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    op = await AiCreditService(session).complete_operation(
        customer.id, operation_id, success=body.success, result=body.result
    )
    return AiOperationResponse.model_validate(op)


@router.get("/ai/operations", response_model=list[AiOperationResponse])
async def list_ai_operations(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> list[AiOperationResponse]:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    ops = await AiCreditService(session).list_operations(customer.id)
    return [AiOperationResponse.model_validate(o) for o in ops]


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> list[NotificationResponse]:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    rows = await NotificationService(session).list_for_customer(customer.id)
    return [NotificationResponse.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> NotificationResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    row = await NotificationService(session).mark_read(customer.id, notification_id)
    return NotificationResponse.model_validate(row)


@router.post("/domains/check", response_model=DomainAvailabilityResponse)
async def check_domain(
    body: DomainAvailabilityRequest,
    settings: SettingsDep,
) -> DomainAvailabilityResponse:
    result = await DomainRegistrar(settings).check(body.name, body.extension)
    return DomainAvailabilityResponse(
        domain=str(result["domain"]),
        available=bool(result["available"]),
        price_yearly=result["price_yearly"],
        currency=str(result.get("currency") or "GHS"),
        message=str(result["message"]),
        provider=str(result.get("provider") or "local"),
    )


@router.post("/subscriptions/{subscription_id}/renew", response_model=SubscriptionResponse)
async def renew_subscription(
    subscription_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> SubscriptionResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    sub = await SubscriptionBillingService(settings, session).renew(customer.id, subscription_id)
    return SubscriptionResponse.model_validate(sub)


@router.post("/subscriptions/{subscription_id}/change-plan", response_model=SubscriptionResponse)
async def change_subscription_plan(
    subscription_id: UUID,
    body: ChangePlanRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> SubscriptionResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    sub = await SubscriptionBillingService(settings, session).change_plan(
        customer.id, subscription_id, body.plan_id
    )
    return SubscriptionResponse.model_validate(sub)


@router.post("/subscriptions/{subscription_id}/auto-renew", response_model=SubscriptionResponse)
async def set_auto_renew(
    subscription_id: UUID,
    body: AutoRenewRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> SubscriptionResponse:
    _require_customer_user(user)
    customer = await CustomerService(settings, session).require_for_user(user.id)
    sub = await SubscriptionBillingService(settings, session).set_auto_renew(
        customer.id, subscription_id, body.enabled
    )
    return SubscriptionResponse.model_validate(sub)


@router.post("/billing/tick")
async def run_billing_tick(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
) -> dict:
    if not (user.is_superuser or Role.ADMIN.value in (user.roles or []) or Role.SUPERADMIN.value in (user.roles or [])):
        raise AuthorizationError("Staff only.")
    return await SubscriptionBillingService(settings, session).tick()


@router.get("/capacity", response_model=list[CapacityNodeResponse])
async def capacity(
    user: CurrentUser,
    session: DbSession,
) -> list[CapacityNodeResponse]:
    # Staff or customer — read-only capacity for transparency
    if not (user.is_superuser or Role.ADMIN.value in (user.roles or []) or Role.SUPERADMIN.value in (user.roles or [])):
        _require_customer_user(user)
    mgr = ResourceManager(session)
    out: list[CapacityNodeResponse] = []
    for node in await mgr.list_nodes():
        snap = await mgr.snapshot(node)
        out.append(CapacityNodeResponse(**snap.__dict__))
    return out
