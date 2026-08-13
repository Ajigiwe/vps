"""IFNOTUS product-layer schemas (catalog, customers, orders, environments)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import SchemaBase


class HostingPlanSchema(SchemaBase):
    id: UUID
    slug: str
    name: str
    cpu_cores: int
    ram_gb: int
    storage_gb: int
    bandwidth_tb: Decimal
    ai_credits: int
    price_monthly: Decimal
    price_yearly: Decimal | None = None
    currency: str
    features: dict
    sort_order: int
    is_active: bool


class HostingPlanListResponse(SchemaBase):
    items: list[HostingPlanSchema]
    brand: str = "IFNOTUS"
    currency: str = "GHS"


class DomainTldPriceSchema(SchemaBase):
    extension: str
    price_yearly: Decimal
    currency: str = "GHS"


class CatalogMetaResponse(SchemaBase):
    brand: str = "IFNOTUS"
    panel_name: str = "IFNOTUS Panel"
    currency: str = "GHS"
    domain_prices: list[DomainTldPriceSchema]
    updated_at: datetime | None = None


class CustomerRegisterRequest(SchemaBase):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = None
    company: str | None = None


class CustomerVerifyEmailRequest(SchemaBase):
    token: str
    code: str = Field(min_length=4, max_length=12)


class CustomerResponse(SchemaBase):
    id: UUID
    email: str
    full_name: str
    phone: str | None = None
    company: str | None = None
    email_verified: bool
    two_factor_enabled: bool
    created_at: datetime


class CustomerRegisterResponse(SchemaBase):
    customer: CustomerResponse
    verification_token: str
    message: str = "Account created. Verify your email with the code sent (or shown in demo)."


class CreateOrderRequest(SchemaBase):
    plan_id: UUID
    domain_name: str | None = None
    domain_extension: str | None = None
    include_domain: bool = True


class OrderResponse(SchemaBase):
    id: UUID
    customer_id: UUID
    plan_id: UUID
    domain_name: str | None = None
    domain_extension: str | None = None
    plan_price: Decimal
    domain_price: Decimal
    total_price: Decimal
    currency: str
    payment_status: str
    provisioning_status: str
    paystack_reference: str | None = None
    paid_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class CreateOrderResponse(SchemaBase):
    order: OrderResponse
    authorization_url: str | None = None
    reference: str
    demo: bool = False
    paystack_public_key: str | None = None


class VerifyPaymentRequest(SchemaBase):
    reference: str


class EnvironmentResponse(SchemaBase):
    id: UUID
    subscription_id: UUID
    customer_id: UUID
    status: str
    cpu_limit: int
    ram_limit_gb: int
    storage_limit_gb: int
    ip_address: str | None = None
    domain: str | None = None
    document_root: str | None = None
    health_status: str
    isolation_type: str = "filesystem"
    container_port: int | None = None
    ssl_expiry: datetime | None = None
    created_at: datetime


class SubscriptionResponse(SchemaBase):
    id: UUID
    customer_id: UUID
    plan_id: UUID
    status: str
    cpu_allocated: int
    ram_allocated: int
    storage_allocated: int
    bandwidth_used_gb: Decimal
    started_at: datetime | None = None
    expires_at: datetime | None = None
    auto_renew: bool
    grace_until: datetime | None = None
    last_reminder_days: int | None = None


class ChangePlanRequest(SchemaBase):
    plan_id: UUID


class AutoRenewRequest(SchemaBase):
    enabled: bool = True


class AiCreditAccountResponse(SchemaBase):
    customer_id: UUID
    credits_remaining: int
    total_allocated: int
    lifetime_used: int


class AiOperationRequest(SchemaBase):
    operation_type: str = Field(pattern="^(build|deploy|fix|audit)$")
    permission_level: int = Field(ge=1, le=4)
    request: str = Field(min_length=3, max_length=8000)
    environment_id: UUID | None = None
    risk_classification: str = "low"


class AiOperationResponse(SchemaBase):
    id: UUID
    customer_id: UUID
    environment_id: UUID | None = None
    operation_type: str
    permission_level: int
    credits_used: int
    status: str
    request: str
    result: str | None = None
    risk_classification: str
    required_confirmation: bool
    completed_at: datetime | None = None
    created_at: datetime


class AiOperationCompleteRequest(SchemaBase):
    success: bool = True
    result: str = Field(min_length=1, max_length=20000)


class NotificationResponse(SchemaBase):
    id: UUID
    title: str
    body: str
    kind: str
    channel: str
    is_read: bool
    created_at: datetime


class CustomerDashboardResponse(SchemaBase):
    brand: str = "IFNOTUS"
    customer: CustomerResponse
    credits: AiCreditAccountResponse
    environments: list[EnvironmentResponse]
    subscriptions: list[SubscriptionResponse]
    unread_notifications: int
    usage: dict


class CapacityNodeResponse(SchemaBase):
    node_id: str
    hostname: str
    cpu_total: int
    ram_total_gb: int
    storage_total_gb: int
    cpu_reserved_pct: int
    cpu_used: int
    ram_used: int
    storage_used: int
    cpu_free: int
    ram_free: int
    storage_free: int
    status: str


class DomainAvailabilityRequest(SchemaBase):
    name: str = Field(min_length=2, max_length=63)
    extension: str = Field(pattern=r"^\.(online|com|net)$")


class DomainAvailabilityResponse(SchemaBase):
    domain: str
    available: bool
    price_yearly: Decimal
    currency: str = "GHS"
    message: str
    provider: str = "local"
