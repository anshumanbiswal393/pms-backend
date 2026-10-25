"""
Part 6 — POS stock, recipe BOM, settle deduction, and inventory reports.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.POS.models import (
    Outlet,
    MenuItem,
    POSOrder,
    POSOrderItem,
    POSStockItem,
    POSRecipe,
    POSRecipeIngredient,
    POSStockMovement,
    POSWastage,
    POSClosingCount,
    POSClosingCountLine,
    POSUnit,
    AggregatorWebhookLog,
)

DEFAULT_INVENTORY_SETTINGS = {
    "recipeBasedConsumption": "Yes",
    "consumptionType": "Both Online and Offline Orders",
    "atParStockNotification": "Yes",
    "minStockOutOfStockNotify": "Yes",
    "notifyKitchenBelowPar": "No",
    "reverseConsumptionCancelled": "Yes",
    "restrictNegativeStockProduction": "Yes",
}

OUT_TYPES = ("OUT", "SETTLE_DEDUCT", "WASTAGE", "PURCHASE_RETURN")
IN_TYPES = ("IN", "SETTLE_REVERSE", "OPENING")


def _d(val, default="0") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    return Decimal(str(val))


class StockService:
    """Stock SKUs, recipes, and settle-time deductions."""

    @classmethod
    def get_inventory_settings(cls, outlet_id=None) -> dict[str, Any]:
        settings = dict(DEFAULT_INVENTORY_SETTINGS)
        if not outlet_id:
            return settings
        outlet = Outlet.objects.filter(pk=outlet_id, deleted_at__isnull=True).first()
        if not outlet:
            return settings
        meta = outlet.meta_settings or {}
        stored = meta.get("inventory") or {}
        settings.update({k: stored[k] for k in DEFAULT_INVENTORY_SETTINGS if k in stored})
        connected = meta.get("connectedServices") or {}
        if connected.get("inventoryConsumption") in ("No", False, "false"):
            settings["recipeBasedConsumption"] = "No"
        elif connected.get("inventoryConsumption") in ("Yes", True, "true"):
            settings["recipeBasedConsumption"] = "Yes"
        return settings

    @classmethod
    def save_inventory_settings(cls, data: dict[str, Any], *, outlet_id=None) -> dict[str, Any]:
        if not outlet_id:
            raise ValidationError({"outlet_id": "outlet_id is required to save inventory settings."})
        outlet = Outlet.objects.filter(pk=outlet_id, deleted_at__isnull=True).first()
        if not outlet:
            raise ValidationError({"outlet": "Outlet not found."})
        meta = dict(outlet.meta_settings or {})
        inventory = dict(meta.get("inventory") or {})
        for key in DEFAULT_INVENTORY_SETTINGS:
            if key in data:
                inventory[key] = data[key]
        meta["inventory"] = inventory
        if "recipeBasedConsumption" in inventory:
            connected = dict(meta.get("connectedServices") or {})
            connected["inventoryConsumption"] = inventory["recipeBasedConsumption"]
            meta["connectedServices"] = connected
        outlet.meta_settings = meta
        outlet.save(update_fields=["meta_settings", "updated_at"])
        return cls.get_inventory_settings(outlet_id)

    @classmethod
    def consumption_enabled(cls, outlet_id=None) -> bool:
        settings = cls.get_inventory_settings(outlet_id)
        return str(settings.get("recipeBasedConsumption", "Yes")).lower() in ("yes", "true", "1")

    @classmethod
    def serialize_stock(cls, item: POSStockItem) -> dict[str, Any]:
        qty = float(item.quantity_on_hand)
        reorder = float(item.reorder_level or 0)
        par = float(getattr(item, "par_level", 0) or 0)
        return {
            "id": str(item.id),
            "code": item.code,
            "name": item.name,
            "rawMaterial": item.name,
            "category": item.category or "",
            "unit": item.unit,
            "availableStock": qty,
            "closingStock": qty,
            "quantityOnHand": qty,
            "parLevel": par,
            "reorderLevel": reorder,
            "minThreshold": reorder,
            "unitCost": float(item.unit_cost or 0),
            "itemKind": getattr(item, "item_kind", None) or "RAW",
            "isFavorite": bool(getattr(item, "is_favorite", False)),
            "isLow": qty <= reorder if reorder > 0 else False,
            "isAtPar": qty <= par if par > 0 else False,
            "isActive": item.is_active,
            "outletId": str(item.outlet_id) if item.outlet_id else None,
            "propertyId": str(item.property_id) if item.property_id else None,
            "externalSkuRef": item.external_sku_ref,
        }

    @classmethod
    def list_stock(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        active_only: bool = True,
        search: str | None = None,
        item_kind: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = POSStockItem.objects.filter(deleted_at__isnull=True)
        if active_only:
            qs = qs.filter(is_active=True)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if item_kind:
            qs = qs.filter(item_kind=item_kind.upper())
        if category and category.lower() != "all":
            qs = qs.filter(category__iexact=category)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)
        return [cls.serialize_stock(i) for i in qs.order_by("name")]

    @classmethod
    def get_item(cls, pk) -> dict[str, Any]:
        item = POSStockItem.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not item:
            raise ValidationError({"stock_item": "Stock item not found."})
        return cls.serialize_stock(item)

    @classmethod
    @transaction.atomic
    def upsert_stock(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        property_id = data.get("property_id") or data.get("propertyId")
        tenant_id = data.get("tenant_id") or data.get("tenantId")
        outlet_id = data.get("outlet_id") or data.get("outletId")
        if outlet_id and (not property_id or not tenant_id):
            outlet = Outlet.objects.filter(pk=outlet_id, deleted_at__isnull=True).first()
            if outlet:
                property_id = property_id or outlet.property_id
                tenant_id = tenant_id or outlet.tenant_id
        code = (data.get("code") or "").strip()
        name = (data.get("name") or data.get("rawMaterial") or "").strip()
        if not property_id or not tenant_id:
            raise ValidationError(
                {"detail": "tenant_id and property_id are required."}
            )
        if not code or not name:
            raise ValidationError({"detail": "code and name are required."})

        item, created = POSStockItem.objects.get_or_create(
            property_id=property_id,
            code=code,
            defaults={
                "tenant_id": tenant_id,
                "outlet_id": outlet_id,
                "name": name,
                "category": data.get("category"),
                "unit": data.get("unit") or "Kg",
                "quantity_on_hand": _d(data.get("quantity_on_hand") or data.get("availableStock") or 0),
                "par_level": _d(data.get("par_level") or data.get("parLevel") or 0),
                "reorder_level": _d(data.get("reorder_level") or data.get("reorderLevel") or data.get("minThreshold") or 0),
                "unit_cost": _d(data.get("unit_cost") or data.get("unitCost") or 0),
                "item_kind": (data.get("item_kind") or data.get("itemKind") or "RAW").upper(),
                "is_favorite": bool(data.get("is_favorite", data.get("isFavorite", False))),
                "external_sku_ref": data.get("external_sku_ref") or data.get("externalSkuRef"),
                "is_active": data.get("is_active", data.get("isActive", True)),
                "created_by": user if getattr(user, "is_authenticated", False) else None,
            },
        )
        if not created:
            cls._apply_item_fields(item, data, outlet_id=outlet_id)
            item.save()
        elif data.get("quantity_on_hand") or data.get("availableStock"):
            opening = _d(data.get("quantity_on_hand") or data.get("availableStock") or 0)
            if opening > 0:
                POSStockMovement.objects.create(
                    stock_item=item,
                    movement_type="OPENING",
                    quantity=opening,
                    balance_after=opening,
                    reference_type="OPENING",
                    notes="Opening stock",
                    created_by=user if getattr(user, "is_authenticated", False) else None,
                    meta={},
                )
        return cls.serialize_stock(item)

    @classmethod
    def _apply_item_fields(cls, item: POSStockItem, data: dict[str, Any], *, outlet_id=None):
        for field, keys in (
            ("name", ("name", "rawMaterial")),
            ("category", ("category",)),
            ("unit", ("unit",)),
            ("external_sku_ref", ("external_sku_ref", "externalSkuRef")),
        ):
            for k in keys:
                if k in data:
                    setattr(item, field, data[k])
                    break
        if "par_level" in data or "parLevel" in data:
            item.par_level = _d(data.get("par_level") or data.get("parLevel") or 0)
        if "reorder_level" in data or "reorderLevel" in data or "minThreshold" in data:
            item.reorder_level = _d(
                data.get("reorder_level") or data.get("reorderLevel") or data.get("minThreshold") or 0
            )
        if "unit_cost" in data or "unitCost" in data:
            item.unit_cost = _d(data.get("unit_cost") or data.get("unitCost") or 0)
        if "item_kind" in data or "itemKind" in data:
            item.item_kind = (data.get("item_kind") or data.get("itemKind") or item.item_kind or "RAW").upper()
        if "is_favorite" in data or "isFavorite" in data:
            item.is_favorite = bool(data.get("is_favorite", data.get("isFavorite", item.is_favorite)))
        if "is_active" in data or "isActive" in data:
            item.is_active = bool(data.get("is_active", data.get("isActive", item.is_active)))
        if outlet_id:
            item.outlet_id = outlet_id

    @classmethod
    @transaction.atomic
    def update_item(cls, pk, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        item = (
            POSStockItem.objects.select_for_update()
            .filter(pk=pk, deleted_at__isnull=True)
            .first()
        )
        if not item:
            raise ValidationError({"stock_item": "Stock item not found."})
        cls._apply_item_fields(item, data, outlet_id=data.get("outlet_id") or data.get("outletId"))
        item.save()
        return cls.serialize_stock(item)

    @classmethod
    def delete_item(cls, pk, *, user=None) -> bool:
        item = POSStockItem.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not item:
            return False
        item.deleted_at = timezone.now()
        item.is_active = False
        item.save(update_fields=["deleted_at", "is_active", "updated_at"])
        return True

    @classmethod
    @transaction.atomic
    def adjust_stock(
        cls,
        stock_item_id,
        *,
        quantity: Decimal,
        movement_type: str = "ADJUST",
        notes: str = "",
        reference_type: str | None = None,
        reference_id=None,
        user=None,
        allow_negative: bool = False,
    ) -> dict[str, Any]:
        item = (
            POSStockItem.objects.select_for_update()
            .filter(pk=stock_item_id, deleted_at__isnull=True)
            .first()
        )
        if not item:
            raise ValidationError({"stock_item": "Stock item not found."})
        qty = _d(quantity)
        movement_type = (movement_type or "ADJUST").upper()

        if movement_type in OUT_TYPES:
            if qty < 0:
                qty = abs(qty)
            new_bal = (Decimal(str(item.quantity_on_hand)) - qty).quantize(Decimal("0.001"))
            if new_bal < 0 and not allow_negative:
                raise ValidationError(
                    {
                        "quantity": (
                            f"Insufficient stock for {item.code}: "
                            f"have {item.quantity_on_hand}, need {qty}"
                        )
                    }
                )
            signed = -qty
        elif movement_type in IN_TYPES:
            if qty < 0:
                qty = abs(qty)
            new_bal = (Decimal(str(item.quantity_on_hand)) + qty).quantize(Decimal("0.001"))
            signed = qty
        else:
            new_bal = (Decimal(str(item.quantity_on_hand)) + qty).quantize(Decimal("0.001"))
            signed = qty
            if new_bal < 0 and not allow_negative:
                raise ValidationError({"quantity": "Adjustment would make stock negative."})

        item.quantity_on_hand = new_bal
        item.save(update_fields=["quantity_on_hand", "updated_at"])
        POSStockMovement.objects.create(
            stock_item=item,
            movement_type=movement_type,
            quantity=abs(signed),
            balance_after=new_bal,
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
            meta={"signed_qty": str(signed)},
        )
        return cls.serialize_stock(item)

    @classmethod
    def reverse_reference(
        cls,
        *,
        reference_type: str,
        reference_id,
        notes: str = "",
        user=None,
        allow_negative: bool = False,
    ) -> list[dict[str, Any]]:
        originals = POSStockMovement.objects.filter(
            reference_type=reference_type,
            reference_id=reference_id,
            deleted_at__isnull=True,
        )
        if not originals.exists():
            return []
        already = POSStockMovement.objects.filter(
            reference_type=f"{reference_type}_REVERSE",
            reference_id=reference_id,
            deleted_at__isnull=True,
        ).exists()
        if already:
            return []
        reversed_rows = []
        for mov in originals:
            signed = _d((mov.meta or {}).get("signed_qty") or 0)
            if signed == 0:
                if mov.movement_type in OUT_TYPES:
                    signed = -_d(mov.quantity)
                else:
                    signed = _d(mov.quantity)
            reverse_qty = -signed
            reverse_type = "IN" if reverse_qty > 0 else "OUT"
            updated = cls.adjust_stock(
                mov.stock_item_id,
                quantity=abs(reverse_qty),
                movement_type=reverse_type,
                notes=notes or f"Reverse {reference_type}",
                reference_type=f"{reference_type}_REVERSE",
                reference_id=reference_id,
                user=user,
                allow_negative=allow_negative,
            )
            reversed_rows.append(updated)
        return reversed_rows

    @classmethod
    def list_movements(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        stock_item_id=None,
        movement_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        qs = POSStockMovement.objects.filter(deleted_at__isnull=True).select_related("stock_item")
        if property_id:
            qs = qs.filter(stock_item__property_id=property_id)
        if outlet_id:
            qs = qs.filter(stock_item__outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(stock_item__tenant_id=tenant_id)
        if stock_item_id:
            qs = qs.filter(stock_item_id=stock_item_id)
        if movement_type and movement_type.upper() != "ALL":
            qs = qs.filter(movement_type=movement_type.upper())
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date[:10])
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date[:10])
        rows = []
        for mov in qs.order_by("-created_at")[:limit]:
            signed = _d((mov.meta or {}).get("signed_qty") or 0)
            if signed == 0:
                signed = -_d(mov.quantity) if mov.movement_type in OUT_TYPES else _d(mov.quantity)
            rows.append(
                {
                    "id": str(mov.id),
                    "stockItemId": str(mov.stock_item_id),
                    "code": mov.stock_item.code,
                    "name": mov.stock_item.name,
                    "unit": mov.stock_item.unit,
                    "type": mov.movement_type,
                    "quantity": float(mov.quantity),
                    "signedQty": float(signed),
                    "balanceAfter": float(mov.balance_after),
                    "referenceType": mov.reference_type,
                    "referenceId": str(mov.reference_id) if mov.reference_id else None,
                    "notes": mov.notes or "",
                    "createdAt": mov.created_at.isoformat() if mov.created_at else None,
                }
            )
        return rows

    @classmethod
    def overview(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> dict[str, Any]:
        items = cls.list_stock(
            property_id=property_id, outlet_id=outlet_id, tenant_id=tenant_id
        )
        low = [i for i in items if i.get("isLow")]
        at_par = [i for i in items if i.get("isAtPar") and not i.get("isLow")]
        valuation = sum(i["availableStock"] * i["unitCost"] for i in items)
        movements = cls.list_movements(
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
            limit=12,
        )
        wastage_today = POSStockMovement.objects.filter(
            deleted_at__isnull=True,
            movement_type="WASTAGE",
            created_at__date=timezone.now().date(),
        )
        if property_id:
            wastage_today = wastage_today.filter(stock_item__property_id=property_id)
        if outlet_id:
            wastage_today = wastage_today.filter(stock_item__outlet_id=outlet_id)
        wastage_qty = float(wastage_today.aggregate(s=Sum("quantity"))["s"] or 0)
        return {
            "success": True,
            "skuActive": len(items),
            "valuation": round(valuation, 2),
            "lowStockCount": len(low),
            "atParCount": len(at_par),
            "critical": len(low),
            "wastageTodayQty": wastage_qty,
            "lowStock": low,
            "atPar": at_par,
            "items": items,
            "movements": movements,
        }

    @classmethod
    def alerts(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> list[dict[str, Any]]:
        settings = cls.get_inventory_settings(outlet_id)
        items = cls.list_stock(
            property_id=property_id, outlet_id=outlet_id, tenant_id=tenant_id
        )
        rows = []
        for item in items:
            if settings.get("minStockOutOfStockNotify") == "Yes" and item.get("isLow"):
                rows.append(
                    {
                        "id": f"low-{item['id']}",
                        "title": "Low stock alert",
                        "message": f"{item['name']} is below the reorder level ({item['availableStock']} {item['unit']}).",
                        "category": "STOCK",
                        "link": "/pos/inventory/available-stock",
                        "stockItemId": item["id"],
                        "severity": "critical",
                    }
                )
            elif settings.get("atParStockNotification") == "Yes" and item.get("isAtPar"):
                rows.append(
                    {
                        "id": f"par-{item['id']}",
                        "title": "At-par stock",
                        "message": f"{item['name']} has reached the at-par stock level.",
                        "category": "STOCK",
                        "link": "/pos/inventory/available-stock",
                        "stockItemId": item["id"],
                        "severity": "warning",
                    }
                )
        return rows

    @classmethod
    def serialize_recipe(cls, recipe: POSRecipe) -> dict[str, Any]:
        return {
            "id": str(recipe.id),
            "menuItemId": str(recipe.menu_item_id) if recipe.menu_item_id else None,
            "menuItemName": recipe.menu_item.name if recipe.menu_item_id else "",
            "menuItem": recipe.menu_item.name if recipe.menu_item_id else (recipe.name or ""),
            "name": recipe.name or (recipe.menu_item.name if recipe.menu_item_id else ""),
            "category": recipe.category or "",
            "yieldQty": float(recipe.yield_qty),
            "yieldUnit": recipe.yield_unit or "portion",
            "prepTimeMinutes": str(recipe.prep_time_minutes or 15),
            "notes": recipe.notes or "",
            "isActive": recipe.is_active,
            "ingredients": [
                {
                    "id": str(line.id),
                    "stockItemId": str(line.stock_item_id),
                    "stockItemCode": line.stock_item.code,
                    "stockItemName": line.stock_item.name,
                    "name": line.stock_item.name,
                    "quantity": float(line.quantity),
                    "unit": line.unit or line.stock_item.unit,
                }
                for line in recipe.ingredients.all()
            ],
        }

    @classmethod
    def list_recipes(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = (
            POSRecipe.objects.filter(deleted_at__isnull=True)
            .select_related("menu_item")
            .prefetch_related("ingredients__stock_item")
        )
        if search:
            qs = qs.filter(name__icontains=search)
        return [cls.serialize_recipe(r) for r in qs.order_by("name")]

    @classmethod
    @transaction.atomic
    def save_recipe(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        recipe_id = data.get("id")
        menu_item_id = data.get("menu_item_id") or data.get("menuItemId")
        name = (data.get("name") or "").strip()
        if recipe_id:
            recipe = POSRecipe.objects.filter(pk=recipe_id, deleted_at__isnull=True).first()
            if not recipe:
                raise ValidationError({"recipe": "Recipe not found."})
        elif menu_item_id:
            menu_item = MenuItem.objects.filter(pk=menu_item_id, deleted_at__isnull=True).first()
            if not menu_item:
                raise ValidationError({"menu_item": "Menu item not found."})
            recipe, _ = POSRecipe.objects.get_or_create(
                menu_item=menu_item,
                defaults={
                    "name": name or menu_item.name,
                    "is_active": True,
                    "created_by": user if getattr(user, "is_authenticated", False) else None,
                },
            )
        else:
            if not name:
                raise ValidationError({"name": "Recipe name is required."})
            recipe = POSRecipe.objects.create(
                name=name,
                is_active=True,
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
        if name:
            recipe.name = name
        if "category" in data:
            recipe.category = data.get("category") or ""
        recipe.yield_qty = _d(data.get("yield_qty") or data.get("yieldQty") or recipe.yield_qty or 1)
        if data.get("yield_unit") or data.get("yieldUnit"):
            recipe.yield_unit = data.get("yield_unit") or data.get("yieldUnit")
        if data.get("prep_time_minutes") or data.get("prepTimeMinutes"):
            recipe.prep_time_minutes = int(data.get("prep_time_minutes") or data.get("prepTimeMinutes") or 15)
        if "notes" in data:
            recipe.notes = data.get("notes") or ""
        if "is_active" in data or "isActive" in data:
            recipe.is_active = bool(data.get("is_active", data.get("isActive", True)))
        recipe.save()

        ingredients = data.get("ingredients")
        if ingredients is not None:
            recipe.ingredients.all().delete()
            for idx, raw in enumerate(ingredients or []):
                stock_id = raw.get("stock_item_id") or raw.get("stockItemId")
                qty = _d(raw.get("quantity") or 0)
                if not stock_id or qty <= 0:
                    continue
                stock = POSStockItem.objects.filter(pk=stock_id, deleted_at__isnull=True).first()
                if not stock:
                    raise ValidationError({"ingredients": f"Stock item {stock_id} not found."})
                POSRecipeIngredient.objects.create(
                    recipe=recipe,
                    stock_item=stock,
                    quantity=qty,
                    unit=raw.get("unit") or stock.unit,
                    sort_order=idx,
                )
        recipe = (
            POSRecipe.objects.filter(pk=recipe.pk)
            .select_related("menu_item")
            .prefetch_related("ingredients__stock_item")
            .first()
        )
        return cls.serialize_recipe(recipe)

    @classmethod
    @transaction.atomic
    def set_recipe(
        cls,
        menu_item_id,
        *,
        ingredients: list[dict],
        name: str | None = None,
        yield_qty: Decimal | float = 1,
        user=None,
    ) -> dict[str, Any]:
        return cls.save_recipe(
            {
                "menuItemId": menu_item_id,
                "name": name,
                "yieldQty": yield_qty,
                "ingredients": ingredients,
            },
            user=user,
        )

    @classmethod
    def delete_recipe(cls, pk, *, user=None) -> bool:
        recipe = POSRecipe.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not recipe:
            recipe = POSRecipe.objects.filter(menu_item_id=pk, deleted_at__isnull=True).first()
        if not recipe:
            return False
        recipe.deleted_at = timezone.now()
        recipe.is_active = False
        recipe.save(update_fields=["deleted_at", "is_active", "updated_at"])
        return True

    @classmethod
    def get_recipe(cls, pk) -> dict[str, Any]:
        recipe = (
            POSRecipe.objects.filter(pk=pk, deleted_at__isnull=True)
            .select_related("menu_item")
            .prefetch_related("ingredients__stock_item")
            .first()
        )
        if not recipe:
            recipe = (
                POSRecipe.objects.filter(menu_item_id=pk, deleted_at__isnull=True)
                .select_related("menu_item")
                .prefetch_related("ingredients__stock_item")
                .first()
            )
        if not recipe:
            raise ValidationError({"recipe": "Recipe not found."})
        return cls.serialize_recipe(recipe)

    @classmethod
    @transaction.atomic
    def deduct_for_order(cls, order: POSOrder, *, user=None) -> dict[str, Any]:
        """
        Deduct BOM ingredients for each order line on settle.
        Skips lines without recipe. Idempotent per order via movement reference.
        """
        if not cls.consumption_enabled(order.outlet_id):
            return {
                "orderId": str(order.id),
                "deducted": False,
                "reason": "recipe_based_consumption_disabled",
            }
        already = POSStockMovement.objects.filter(
            reference_type="POS_ORDER",
            reference_id=order.id,
            movement_type="SETTLE_DEDUCT",
        ).exists()
        if already:
            return {"orderId": str(order.id), "deducted": False, "reason": "already_deducted"}

        lines = POSOrderItem.objects.filter(
            order=order, is_void=False, deleted_at__isnull=True
        ).select_related("menu_item")
        deductions = []
        for line in lines:
            if not line.menu_item_id:
                continue
            recipe = (
                POSRecipe.objects.filter(
                    menu_item_id=line.menu_item_id,
                    is_active=True,
                    deleted_at__isnull=True,
                )
                .prefetch_related("ingredients__stock_item")
                .first()
            )
            if not recipe:
                continue
            portions = Decimal(str(line.quantity)) / Decimal(str(recipe.yield_qty or 1))
            for ing in recipe.ingredients.all():
                need = (Decimal(str(ing.quantity)) * portions).quantize(Decimal("0.001"))
                if need <= 0:
                    continue
                updated = cls.adjust_stock(
                    ing.stock_item_id,
                    quantity=need,
                    movement_type="SETTLE_DEDUCT",
                    notes=f"Settle {order.order_number} · {line.item_name}",
                    reference_type="POS_ORDER",
                    reference_id=order.id,
                    user=user,
                )
                deductions.append(
                    {
                        "stockItemId": updated["id"],
                        "code": updated["code"],
                        "quantity": float(need),
                        "balanceAfter": updated["quantityOnHand"],
                    }
                )
        return {
            "orderId": str(order.id),
            "orderNumber": order.order_number,
            "deducted": True,
            "lines": deductions,
            "count": len(deductions),
        }

    @classmethod
    @transaction.atomic
    def reverse_for_order(cls, order: POSOrder, *, user=None) -> dict[str, Any]:
        deducted = POSStockMovement.objects.filter(
            reference_type="POS_ORDER",
            reference_id=order.id,
            movement_type="SETTLE_DEDUCT",
        )
        if not deducted.exists():
            return {"orderId": str(order.id), "reversed": False, "reason": "not_deducted"}
        already = POSStockMovement.objects.filter(
            reference_type="POS_ORDER",
            reference_id=order.id,
            movement_type="SETTLE_REVERSE",
        ).exists()
        if already:
            return {"orderId": str(order.id), "reversed": False, "reason": "already_reversed"}
        restored = []
        for mov in deducted:
            updated = cls.adjust_stock(
                mov.stock_item_id,
                quantity=mov.quantity,
                movement_type="SETTLE_REVERSE",
                notes=f"Reverse settle {order.order_number}",
                reference_type="POS_ORDER",
                reference_id=order.id,
                user=user,
            )
            restored.append(updated)
        return {"orderId": str(order.id), "reversed": True, "count": len(restored)}

    # ----- Units -----
    @classmethod
    def serialize_unit(cls, unit: POSUnit) -> dict[str, Any]:
        return {
            "id": str(unit.id),
            "name": unit.name,
            "symbol": unit.symbol,
            "type": unit.unit_type,
            "baseUnit": unit.base_symbol or unit.symbol,
            "baseSymbol": unit.base_symbol,
            "ratio": f"1 {unit.symbol} = {unit.ratio_to_base} {unit.base_symbol or unit.symbol}",
            "ratioToBase": float(unit.ratio_to_base),
            "isActive": unit.is_active,
        }

    DEFAULT_UNITS = [
        {"id": "U-1", "name": "Kilogram", "symbol": "kg", "type": "Weight", "baseUnit": "Gram (g)", "ratio": "1 kg = 1000 g", "ratioToBase": 1000, "isActive": True},
        {"id": "U-2", "name": "Gram", "symbol": "g", "type": "Weight", "baseUnit": "Gram (g)", "ratio": "1 g = 1 g", "ratioToBase": 1, "isActive": True},
        {"id": "U-3", "name": "Liter", "symbol": "L", "type": "Volume", "baseUnit": "Milliliter (ml)", "ratio": "1 L = 1000 ml", "ratioToBase": 1000, "isActive": True},
        {"id": "U-4", "name": "Milliliter", "symbol": "ml", "type": "Volume", "baseUnit": "Milliliter (ml)", "ratio": "1 ml = 1 ml", "ratioToBase": 1, "isActive": True},
        {"id": "U-5", "name": "Pieces", "symbol": "pcs", "type": "Count", "baseUnit": "Pieces", "ratio": "1 pcs = 1 pcs", "ratioToBase": 1, "isActive": True},
        {"id": "U-6", "name": "Portion", "symbol": "portion", "type": "Serving", "baseUnit": "Portion", "ratio": "1 portion = 1 portion", "ratioToBase": 1, "isActive": True},
    ]

    @classmethod
    def list_units(cls, *, property_id=None, tenant_id=None) -> list[dict[str, Any]]:
        qs = POSUnit.objects.filter(deleted_at__isnull=True, is_active=True)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        custom_units = [cls.serialize_unit(u) for u in qs.order_by("name")]

        # Always include standard units along with any custom units
        combined = [dict(u) for u in cls.DEFAULT_UNITS]
        existing_symbols = {u["symbol"].lower() for u in combined}
        for cu in custom_units:
            if cu["symbol"].lower() not in existing_symbols:
                combined.append(cu)
                existing_symbols.add(cu["symbol"].lower())
            else:
                combined = [cu if u["symbol"].lower() == cu["symbol"].lower() else u for u in combined]
        return combined

    @classmethod
    def save_unit(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        unit_id = data.get("id")
        name = (data.get("name") or "").strip()
        symbol = (data.get("symbol") or "").strip()
        if not name or not symbol:
            raise ValidationError({"detail": "name and symbol are required."})
        fields = {
            "name": name,
            "symbol": symbol,
            "unit_type": data.get("type") or data.get("unit_type") or "Weight",
            "base_symbol": data.get("baseSymbol") or data.get("base_symbol") or data.get("baseUnit"),
            "ratio_to_base": _d(data.get("ratioToBase") or data.get("ratio_to_base") or 1),
            "property_id": data.get("property_id") or data.get("propertyId"),
            "tenant_id": data.get("tenant_id") or data.get("tenantId"),
            "is_active": data.get("is_active", data.get("isActive", True)),
        }
        if unit_id:
            unit = POSUnit.objects.filter(pk=unit_id, deleted_at__isnull=True).first()
            if not unit:
                raise ValidationError({"unit": "Unit not found."})
            for k, v in fields.items():
                setattr(unit, k, v)
            unit.save()
        else:
            unit = POSUnit.objects.create(
                **fields,
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
        return cls.serialize_unit(unit)

    @classmethod
    def delete_unit(cls, pk) -> bool:
        unit = POSUnit.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not unit:
            return False
        unit.deleted_at = timezone.now()
        unit.is_active = False
        unit.save(update_fields=["deleted_at", "is_active", "updated_at"])
        return True

    # ----- Wastage -----
    @classmethod
    def serialize_wastage(cls, row: POSWastage) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "stockItemId": str(row.stock_item_id),
            "item": row.stock_item.name,
            "category": row.stock_item.category or "",
            "quantity": f"{float(row.quantity)} {row.unit or row.stock_item.unit}",
            "quantityValue": float(row.quantity),
            "unit": row.unit or row.stock_item.unit,
            "costValue": float(row.cost_value),
            "cost": f"₹ {float(row.cost_value):,.0f}",
            "reason": row.reason,
            "approvedBy": row.approved_by or "",
            "date": row.wastage_date.strftime("%d %b %Y") if row.wastage_date else "",
            "dateKey": str(row.wastage_date) if row.wastage_date else "",
            "notes": row.notes or "",
        }

    @classmethod
    def list_wastage(cls, *, property_id=None, outlet_id=None, tenant_id=None) -> list[dict[str, Any]]:
        qs = POSWastage.objects.filter(deleted_at__isnull=True).select_related("stock_item")
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return [cls.serialize_wastage(r) for r in qs.order_by("-wastage_date", "-created_at")]

    @classmethod
    @transaction.atomic
    def create_wastage(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        stock_id = data.get("stockItemId") or data.get("stock_item_id")
        qty = _d(data.get("quantity") or data.get("quantityValue") or 0)
        if not stock_id or qty <= 0:
            raise ValidationError({"detail": "stockItemId and quantity are required."})
        item = POSStockItem.objects.filter(pk=stock_id, deleted_at__isnull=True).first()
        if not item:
            raise ValidationError({"stock_item": "Stock item not found."})
        raw_date = data.get("date") or data.get("wastage_date")
        if raw_date:
            try:
                wdate = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                wdate = timezone.now().date()
        else:
            wdate = timezone.now().date()
        cost = _d(data.get("costValue") or data.get("cost_value") or (qty * (item.unit_cost or 0)))
        row = POSWastage.objects.create(
            tenant_id=data.get("tenant_id") or data.get("tenantId"),
            property_id=data.get("property_id") or data.get("propertyId"),
            outlet_id=data.get("outlet_id") or data.get("outletId"),
            stock_item=item,
            quantity=qty,
            unit=data.get("unit") or item.unit,
            reason=data.get("reason") or "Spoiled / Overripe",
            approved_by=data.get("approvedBy") or data.get("approved_by"),
            wastage_date=wdate,
            notes=data.get("notes") or "",
            cost_value=cost,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        cls.adjust_stock(
            item.id,
            quantity=qty,
            movement_type="WASTAGE",
            notes=f"Wastage {row.reason}",
            reference_type="WASTAGE",
            reference_id=row.id,
            user=user,
        )
        row.is_stock_deducted = True
        row.save(update_fields=["is_stock_deducted", "updated_at"])
        return cls.serialize_wastage(row)

    @classmethod
    @transaction.atomic
    def delete_wastage(cls, pk, *, user=None) -> bool:
        row = POSWastage.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not row:
            return False
        if row.is_stock_deducted:
            cls.reverse_reference(
                reference_type="WASTAGE",
                reference_id=row.id,
                notes=f"Reverse wastage {row.reason}",
                user=user,
            )
        row.deleted_at = timezone.now()
        row.save(update_fields=["deleted_at", "updated_at"])
        return True

    # ----- Closing count -----
    @classmethod
    def get_closing(cls, *, business_date: date, property_id=None, outlet_id=None, tenant_id=None) -> dict[str, Any]:
        items = cls.list_stock(property_id=property_id, outlet_id=outlet_id, tenant_id=tenant_id)
        closing = POSClosingCount.objects.filter(
            business_date=business_date,
            deleted_at__isnull=True,
        )
        if property_id:
            closing = closing.filter(property_id=property_id)
        if outlet_id:
            closing = closing.filter(outlet_id=outlet_id)
        closing = closing.prefetch_related("lines").first()
        counted = {str(line.stock_item_id): line for line in (closing.lines.all() if closing else [])}
        rows = []
        for item in items:
            line = counted.get(item["id"])
            rows.append(
                {
                    **item,
                    "closingStock": item["availableStock"],
                    "newStock": float(line.counted_qty) if line else None,
                    "variance": float(line.variance) if line else None,
                    "notes": line.notes if line else "",
                    "isPosted": bool(closing and closing.is_posted),
                }
            )
        return {
            "success": True,
            "businessDate": str(business_date),
            "isPosted": bool(closing and closing.is_posted),
            "items": rows,
        }

    @classmethod
    @transaction.atomic
    def save_closing(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        raw_date = data.get("business_date") or data.get("businessDate") or data.get("date")
        if not raw_date:
            raise ValidationError({"business_date": "business_date is required (YYYY-MM-DD)."})
        business_date = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
        property_id = data.get("property_id") or data.get("propertyId")
        outlet_id = data.get("outlet_id") or data.get("outletId")
        tenant_id = data.get("tenant_id") or data.get("tenantId")
        entries = data.get("entries") or data.get("items") or []
        if not entries:
            raise ValidationError({"entries": "At least one counted line is required."})

        closing, _ = POSClosingCount.objects.get_or_create(
            property_id=property_id,
            outlet_id=outlet_id,
            business_date=business_date,
            defaults={
                "tenant_id": tenant_id,
                "notes": data.get("notes") or "",
                "created_by": user if getattr(user, "is_authenticated", False) else None,
            },
        )
        if closing.is_posted:
            raise ValidationError({"closing": "This date is already posted. Reverse first to recount."})

        closing.lines.all().delete()
        for raw in entries:
            stock_id = raw.get("id") or raw.get("stockItemId") or raw.get("stock_item_id")
            counted = _d(raw.get("newStock") or raw.get("countedQty") or raw.get("counted_qty"))
            if not stock_id:
                continue
            item = POSStockItem.objects.select_for_update().filter(pk=stock_id, deleted_at__isnull=True).first()
            if not item:
                continue
            system_qty = Decimal(str(item.quantity_on_hand))
            variance = (counted - system_qty).quantize(Decimal("0.001"))
            POSClosingCountLine.objects.create(
                closing=closing,
                stock_item=item,
                system_qty=system_qty,
                counted_qty=counted,
                variance=variance,
                notes=raw.get("notes") or "",
            )
            if variance != 0:
                cls.adjust_stock(
                    item.id,
                    quantity=variance,
                    movement_type="CLOSING",
                    notes=f"Daily stock count {business_date}",
                    reference_type="CLOSING",
                    reference_id=closing.id,
                    user=user,
                    allow_negative=True,
                )
        closing.is_posted = True
        closing.save(update_fields=["is_posted", "updated_at"])
        return cls.get_closing(
            business_date=business_date,
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
        )


class ReportService:
    """Advanced POS reports (sales / stock / consumption)."""

    @classmethod
    def sales_report(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        limit: int = 100,
        start_date=None,
        end_date=None,
        kind: str = "items",
    ) -> dict[str, Any]:
        from apps.POS.services.reports import SalesAnalyticsService

        return SalesAnalyticsService.run(
            kind=kind,
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @classmethod
    def stock_report(cls, **scope) -> dict[str, Any]:
        items = StockService.list_stock(**scope)
        low = [i for i in items if i.get("isLow")]
        return {
            "success": True,
            "count": len(items),
            "lowStockCount": len(low),
            "items": items,
            "lowStock": low,
        }

    @classmethod
    def consumption_report(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        limit: int = 100,
        start_date=None,
        end_date=None,
    ) -> dict[str, Any]:
        qs = POSStockMovement.objects.filter(
            deleted_at__isnull=True,
            movement_type__in=("SETTLE_DEDUCT", "WASTAGE", "OUT"),
        ).select_related("stock_item")
        if property_id:
            qs = qs.filter(stock_item__property_id=property_id)
        if outlet_id:
            qs = qs.filter(stock_item__outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(stock_item__tenant_id=tenant_id)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        rows = (
            qs.values(
                "stock_item_id",
                "stock_item__code",
                "stock_item__name",
                "stock_item__unit",
                "stock_item__category",
            )
            .annotate(qty=Sum("quantity"))
            .order_by("-qty")[:limit]
        )
        items = [
            {
                "stockItemId": str(r["stock_item_id"]),
                "code": r["stock_item__code"],
                "name": r["stock_item__name"],
                "item": r["stock_item__name"],
                "category": r["stock_item__category"] or "",
                "unit": r["stock_item__unit"],
                "consumedQty": float(r["qty"] or 0),
                "qtyUsed": float(r["qty"] or 0),
            }
            for r in rows
        ]
        return {"success": True, "count": len(items), "items": items}


class AggregatorWebhookService:
    """Stub receiver for Zomato/Swiggy webhooks (audit only for now)."""

    @classmethod
    def receive(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        provider = (
            data.get("provider")
            or data.get("source")
            or "UNKNOWN"
        ).upper()
        log = AggregatorWebhookLog.objects.create(
            tenant_id=data.get("tenant_id") or data.get("tenantId"),
            property_id=data.get("property_id") or data.get("propertyId"),
            provider=provider,
            event_type=data.get("event_type") or data.get("eventType") or data.get("event"),
            external_order_id=data.get("external_order_id")
            or data.get("externalOrderId")
            or data.get("order_id"),
            payload=data,
            status="RECEIVED",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        return {
            "success": True,
            "id": str(log.id),
            "provider": log.provider,
            "status": log.status,
            "message": "Webhook accepted (stub — order sync not yet enabled).",
        }
