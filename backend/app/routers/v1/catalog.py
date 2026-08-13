"""Public Podium catalog — plans and domain TLD prices."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.platform import HostingPlan
from app.schemas.platform import (
    CatalogMetaResponse,
    DomainTldPriceSchema,
    HostingPlanListResponse,
    HostingPlanSchema,
)

router = APIRouter()

DOMAIN_PRICES = [
    DomainTldPriceSchema(extension=".online", price_yearly=50),
    DomainTldPriceSchema(extension=".net", price_yearly=200),
    DomainTldPriceSchema(extension=".com", price_yearly=250),
]


@router.get("/plans", response_model=HostingPlanListResponse)
async def list_plans(session: DbSession) -> HostingPlanListResponse:
    result = await session.execute(
        select(HostingPlan).where(HostingPlan.is_active.is_(True)).order_by(HostingPlan.sort_order)
    )
    plans = list(result.scalars().all())
    return HostingPlanListResponse(items=[HostingPlanSchema.model_validate(p) for p in plans])


@router.get("/meta", response_model=CatalogMetaResponse)
async def catalog_meta() -> CatalogMetaResponse:
    return CatalogMetaResponse(domain_prices=DOMAIN_PRICES)
