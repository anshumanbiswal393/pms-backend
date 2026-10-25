"""
Part 2 — Menu catalog service (POS-owned, PostgreSQL).

Builds billing-ready catalog DTOs from MenuCategory / MenuItem / variants.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import Prefetch, Q

from apps.POS.models import MenuCategory, MenuItem, MenuVariant, TaxProfile


ITEM_TYPE_UI = {
    "VEG": "Veg",
    "NON_VEG": "Non-Veg",
    "EGG": "Egg",
}

STATUS_UI = {
    "ACTIVE": "Active",
    "INACTIVE": "Inactive",
}


class MenuCatalogService:
    """Read/helpers for POS menu catalog APIs."""

    @classmethod
    def item_queryset(cls, *, outlet_id: str | UUID | None = None, active_only: bool = False):
        qs = (
            MenuItem.objects.filter(deleted_at__isnull=True)
            .select_related("outlet", "category", "tax_profile")
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=MenuVariant.objects.filter(
                        deleted_at__isnull=True, is_active=True
                    ).order_by("sort_order", "name"),
                ),
                "modifier_groups__options",
            )
            .order_by("sort_order", "name")
        )
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if active_only:
            qs = qs.filter(status="ACTIVE", category__is_active=True)
        return qs

    @classmethod
    def category_queryset(cls, *, outlet_id: str | UUID | None = None, active_only: bool = False):
        qs = (
            MenuCategory.objects.filter(deleted_at__isnull=True)
            .select_related("outlet", "parent")
            .order_by("sort_order", "name")
        )
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if active_only:
            qs = qs.filter(is_active=True)
        return qs

    @classmethod
    def serialize_item_ui(cls, item: MenuItem) -> dict[str, Any]:
        """Shape matching POS UI `MenuItem` type (camelCase)."""
        tax_rate = item.tax_rate
        if isinstance(tax_rate, Decimal):
            tax_rate_num = float(tax_rate)
        else:
            tax_rate_num = float(tax_rate or 0)

        variants = [
            {
                "id": str(v.id),
                "name": v.name,
                "price": float(v.price),
            }
            for v in item.variants.all()
        ]

        images = item.images if isinstance(item.images, list) else []

        next_available = None
        if item.next_available_at:
            next_available = item.next_available_at.isoformat()

        return {
            "id": str(item.id),
            "outletId": str(item.outlet_id),
            "code": item.code,
            "name": item.name,
            "onlineDisplayName": item.online_display_name or item.name,
            "category": item.category.name if item.category_id else "",
            "categoryId": str(item.category_id) if item.category_id else None,
            "itemType": ITEM_TYPE_UI.get(item.item_type, item.item_type),
            "price": float(item.price),
            "taxRate": tax_rate_num,
            "taxProfileId": str(item.tax_profile_id) if item.tax_profile_id else None,
            "status": STATUS_UI.get(item.status, item.status),
            "description": item.description or "",
            "images": images,
            "variants": variants,
            "modifierGroups": [
                {
                    "id": str(g.id),
                    "name": g.name,
                    "minSelect": g.min_select,
                    "maxSelect": g.max_select,
                    "isRequired": g.is_required,
                    "options": [
                        {
                            "id": str(o.id),
                            "name": o.name,
                            "price": float(o.price),
                        }
                        for o in g.options.filter(deleted_at__isnull=True, is_active=True)
                    ],
                }
                for g in item.modifier_groups.filter(deleted_at__isnull=True, is_active=True)
            ],
            "baseMenu": item.base_menu,
            "zomato": item.zomato,
            "swiggy": item.swiggy,
            "direct": item.direct,
            "nextAvailableTime": next_available,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else "",
            **cls._commission_ui(item),
        }

    @classmethod
    def _commission_ui(cls, item: MenuItem) -> dict[str, Any]:
        meta = getattr(item, "meta", None)
        meta = meta if isinstance(meta, dict) else {}
        raw = meta.get("commission") if isinstance(meta.get("commission"), dict) else {}
        type_key = str(raw.get("type") or "NONE").upper()
        type_ui = {
            "NONE": "Not Configured",
            "PERCENT": "Percentage",
            "FIXED": "Fixed Amount",
        }.get(type_key, "Not Configured")
        value = raw.get("value")
        try:
            value_num = float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            value_num = None
        return {
            "commissionType": type_ui,
            "commissionValue": value_num,
        }

    @classmethod
    def list_items_ui(
        cls,
        *,
        outlet_id: str | UUID | None = None,
        active_only: bool = False,
        search: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = cls.item_queryset(outlet_id=outlet_id, active_only=active_only)
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(code__icontains=search)
                | Q(online_display_name__icontains=search)
            )
        if category:
            qs = qs.filter(Q(category_id=category) | Q(category__name__iexact=category))
        return [cls.serialize_item_ui(item) for item in qs]

    @classmethod
    def billing_catalog(
        cls,
        *,
        outlet_id: str | UUID | None = None,
    ) -> dict[str, Any]:
        """Active catalog grouped by category for billing screen."""
        categories = cls.category_queryset(outlet_id=outlet_id, active_only=True)
        items = cls.list_items_ui(outlet_id=outlet_id, active_only=True)
        by_cat: dict[str, list] = {}
        for item in items:
            by_cat.setdefault(item["category"] or "Uncategorized", []).append(item)

        return {
            "outletId": str(outlet_id) if outlet_id else None,
            "count": len(items),
            "categories": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "onlineDisplayName": c.online_display_name or c.name,
                    "sortOrder": c.sort_order,
                    "itemCount": len(by_cat.get(c.name, [])),
                }
                for c in categories
            ],
            "items": items,
        }

    @classmethod
    def resolve_or_create_tax_profile(
        cls,
        *,
        tenant_id,
        rate: Decimal | float | str,
        property_id=None,
    ) -> TaxProfile:
        rate_dec = Decimal(str(rate))
        code = f"GST{int(rate_dec)}" if rate_dec == rate_dec.to_integral_value() else f"GST{rate_dec}"
        half = (rate_dec / Decimal("2")).quantize(Decimal("0.01"))
        profile, _ = TaxProfile.objects.get_or_create(
            tenant_id=tenant_id,
            code=code,
            defaults={
                "property_id": property_id,
                "name": f"GST {rate_dec}%",
                "rate": rate_dec,
                "cgst_rate": half,
                "sgst_rate": half,
                "igst_rate": Decimal("0.00"),
                "is_active": True,
            },
        )
        return profile
