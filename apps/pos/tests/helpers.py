import uuid

from apps.core.tenants.models import Property, Tenant, TenantConfiguration
from apps.POS.models import Outlet, POSStockItem
from apps.POS.services.stock import StockService


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


def make_tenant_property_outlet(suffix: str | None = None):
    suffix = suffix or unique_suffix()
    tenant = Tenant.objects.create(
        name=f"Stock Test {suffix}",
        subdomain=f"stock-{suffix}",
        country="India",
        currency="INR",
        timezone="Asia/Kolkata",
    )
    TenantConfiguration.objects.create(tenant=tenant, enforce_ip_whitelist=False)
    prop = Property(
        tenant=tenant,
        name=f"Stock Property {suffix}",
        address_line_1="1 Test Street",
        city="Pune",
        state="MH",
        country="India",
        postal_code="411001",
        contact_email=f"stock-{suffix}@retrod.test",
        contact_phone="9999999999",
        currency="INR",
        timezone="Asia/Kolkata",
    )
    prop._skip_booking_sync = True
    prop.save()
    outlet = Outlet.objects.create(
        tenant=tenant,
        property=prop,
        code=f"OUT-{suffix[:8]}",
        name=f"Kitchen {suffix}",
    )
    return tenant, prop, outlet


def make_sku(
    *,
    tenant,
    prop,
    outlet,
    code: str,
    name: str,
    qty: float = 0,
    reorder: float = 0,
    par: float = 0,
    unit_cost: float = 10,
    kind: str = "RAW",
) -> POSStockItem:
    item = POSStockItem.objects.create(
        tenant=tenant,
        property=prop,
        outlet=outlet,
        code=code,
        name=name,
        category="Groceries",
        unit="Kg",
        quantity_on_hand=0,
        reorder_level=reorder,
        par_level=par,
        unit_cost=unit_cost,
        item_kind=kind,
        is_active=True,
    )
    if qty:
        StockService.adjust_stock(
            item.id,
            quantity=qty,
            movement_type="IN",
            notes="Opening",
            reference_type="OPENING",
            reference_id=item.id,
        )
        item.refresh_from_db()
    return item
