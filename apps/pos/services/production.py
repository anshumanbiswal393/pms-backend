"""
POS Food Preparation / Production service.
Manages preparation recipes (BOM) and batch execution with automatic inventory deduction.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.POS.models import (
    Outlet,
    POSStockItem,
    POSStockMovement,
    ProductionRecipe,
    ProductionRecipeIngredient,
    ProductionBatch,
    ProductionBatchIngredient,
)
from apps.POS.services.stock import StockService


class ProductionService:
    """Production recipes and execution runs."""

    @classmethod
    def serialize_recipe(cls, recipe: ProductionRecipe) -> dict[str, Any]:
        ingredients = [
            {
                "id": str(line.id),
                "stockItemId": str(line.stock_item_id),
                "stockItemCode": line.stock_item.code,
                "stockItemName": line.stock_item.name,
                "quantity": float(line.quantity),
                "unit": line.unit or line.stock_item.unit,
                "unitCost": float(line.unit_cost or line.stock_item.unit_cost or 0),
                "lineCost": float((line.quantity * (line.unit_cost or line.stock_item.unit_cost or Decimal("0"))).quantize(Decimal("0.01"))),
            }
            for line in recipe.ingredients.all()
        ]
        total_ing_cost = sum(ing["lineCost"] for ing in ingredients)
        expected_yield = float(recipe.expected_yield or 1)
        cost_per_unit = round(total_ing_cost / expected_yield, 2) if expected_yield > 0 else 0

        return {
            "id": str(recipe.id),
            "code": recipe.code,
            "name": recipe.name,
            "category": recipe.category or "Gravies & Sauces",
            "outputUnit": recipe.output_unit,
            "expectedYield": expected_yield,
            "standardCost": float(recipe.standard_cost or total_ing_cost),
            "costPerUnit": cost_per_unit,
            "shelfLifeDays": recipe.shelf_life_days,
            "instructions": recipe.instructions or "",
            "rawMaterialsCount": len(ingredients),
            "ingredientsSummary": ", ".join(f"{i['stockItemName']} ({i['quantity']}{i['unit']})" for i in ingredients[:4]) + (f" +{len(ingredients) - 4} more" if len(ingredients) > 4 else ""),
            "outputStockItemId": str(recipe.output_stock_item_id) if recipe.output_stock_item_id else None,
            "outputStockItemName": recipe.output_stock_item.name if recipe.output_stock_item else None,
            "isActive": recipe.is_active,
            "ingredients": ingredients,
            "createdAt": recipe.created_at.isoformat() if recipe.created_at else None,
        }

    @classmethod
    def list_recipes(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        category: str | None = None,
        search: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        qs = ProductionRecipe.objects.filter(deleted_at__isnull=True).prefetch_related(
            "ingredients__stock_item", "output_stock_item"
        )
        if active_only:
            qs = qs.filter(is_active=True)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if category and category.lower() != "all":
            qs = qs.filter(category__iexact=category)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)

        recipes = [cls.serialize_recipe(r) for r in qs.order_by("name")]

        # Demo fallback only when no property/outlet is scoped (Highway mock).
        if (
            not recipes
            and not search
            and (not category or category.lower() == "all")
            and not property_id
            and not outlet_id
        ):
            recipes = cls.get_default_seed_recipes()

        return recipes

    @classmethod
    @transaction.atomic
    def save_recipe(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        recipe_id = data.get("id")
        code = (data.get("code") or "").strip()
        name = (data.get("name") or "").strip()
        category = (data.get("category") or "Gravies & Sauces").strip()
        output_unit = data.get("output_unit") or data.get("outputUnit") or "Liter (L)"
        expected_yield = Decimal(str(data.get("expected_yield") or data.get("expectedYield") or 1))
        shelf_life_days = int(data.get("shelf_life_days") or data.get("shelfLifeDays") or 3)
        instructions = data.get("instructions") or ""
        property_id = data.get("property_id") or data.get("propertyId")
        tenant_id = data.get("tenant_id") or data.get("tenantId")
        outlet_id = data.get("outlet_id") or data.get("outletId")
        output_stock_item_id = data.get("output_stock_item_id") or data.get("outputStockItemId")

        if not name:
            raise ValidationError({"name": "Recipe name is required."})
        if not output_stock_item_id and property_id and tenant_id:
            code_base = (code or name).upper().replace(" ", "-")[:24]
            sku_code = f"PREP-{code_base}"
            sku, _ = POSStockItem.objects.get_or_create(
                property_id=property_id,
                code=sku_code,
                defaults={
                    "tenant_id": tenant_id,
                    "outlet_id": outlet_id,
                    "name": name,
                    "category": category,
                    "unit": output_unit,
                    "item_kind": "PREPARED",
                    "is_active": True,
                    "created_by": user if getattr(user, "is_authenticated", False) else None,
                },
            )
            output_stock_item_id = str(sku.id)
        elif not output_stock_item_id:
            raise ValidationError(
                {"outputStockItemId": "Prepared output stock item is required so completed batches can add gravy/atta stock."}
            )

        if not code:
            # Generate code PRD-REC-XX
            count = ProductionRecipe.objects.count() + 1
            code = f"PRD-REC-{count:02d}"

        if recipe_id:
            recipe = ProductionRecipe.objects.filter(pk=recipe_id, deleted_at__isnull=True).first()
            if not recipe:
                raise ValidationError({"recipe": "Recipe not found."})
            recipe.name = name
            recipe.code = code
            recipe.category = category
            recipe.output_unit = output_unit
            recipe.expected_yield = expected_yield
            recipe.shelf_life_days = shelf_life_days
            recipe.instructions = instructions
            if output_stock_item_id:
                recipe.output_stock_item_id = output_stock_item_id
        else:
            recipe = ProductionRecipe.objects.create(
                tenant_id=tenant_id,
                property_id=property_id,
                outlet_id=outlet_id,
                code=code,
                name=name,
                category=category,
                output_unit=output_unit,
                expected_yield=expected_yield,
                shelf_life_days=shelf_life_days,
                instructions=instructions,
                output_stock_item_id=output_stock_item_id,
                is_active=True,
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

        # Update ingredients
        raw_ingredients = data.get("ingredients") or []
        if raw_ingredients is not None:
            recipe.ingredients.all().delete()
            total_cost = Decimal("0")
            for idx, item in enumerate(raw_ingredients):
                stock_item_id = item.get("stock_item_id") or item.get("stockItemId")
                qty = Decimal(str(item.get("quantity") or 0))
                if not stock_item_id or qty <= 0:
                    continue
                stock_item = POSStockItem.objects.filter(pk=stock_item_id, deleted_at__isnull=True).first()
                if not stock_item:
                    continue
                unit_cost = Decimal(str(item.get("unit_cost") or item.get("unitCost") or stock_item.unit_cost or 0))
                total_cost += (qty * unit_cost)
                ProductionRecipeIngredient.objects.create(
                    recipe=recipe,
                    stock_item=stock_item,
                    quantity=qty,
                    unit=item.get("unit") or stock_item.unit,
                    unit_cost=unit_cost,
                    sort_order=idx,
                )
            recipe.standard_cost = total_cost
            recipe.save(update_fields=["standard_cost", "updated_at"])

        return cls.serialize_recipe(recipe)

    @classmethod
    @transaction.atomic
    def delete_recipe(cls, recipe_id, *, user=None) -> bool:
        recipe = ProductionRecipe.objects.filter(pk=recipe_id, deleted_at__isnull=True).first()
        if not recipe:
            return False
        recipe.deleted_at = timezone.now()
        recipe.is_active = False
        recipe.save(update_fields=["deleted_at", "is_active", "updated_at"])
        return True

    @classmethod
    def serialize_batch(cls, batch: ProductionBatch) -> dict[str, Any]:
        ingredients = [
            {
                "id": str(i.id),
                "stockItemId": str(i.stock_item_id),
                "stockItemCode": i.stock_item.code,
                "stockItemName": i.stock_item.name,
                "standardQuantity": float(i.standard_quantity),
                "actualQuantity": float(i.actual_quantity),
                "unit": i.unit,
                "unitCost": float(i.unit_cost),
                "totalCost": float(i.total_cost),
            }
            for i in batch.ingredients_consumed.all()
        ]
        summary = ", ".join(f"{i['stockItemName']} ({i['actualQuantity']}{i['unit']})" for i in ingredients[:3])
        if len(ingredients) > 3:
            summary += f" +{len(ingredients) - 3} more"

        yield_qty = float(batch.yield_quantity)
        total_cost = float(batch.total_cost)
        unit_cost = round(total_cost / yield_qty, 2) if yield_qty > 0 else 0

        return {
            "id": str(batch.id),
            "batchNumber": batch.batch_number,
            "recipeId": str(batch.recipe_id),
            "recipeName": batch.recipe.name if batch.recipe else "",
            "recipeCode": batch.recipe.code if batch.recipe else "",
            "category": batch.recipe.category if batch.recipe else "",
            "preparationDate": batch.preparation_date.strftime("%d %b %Y") if batch.preparation_date else "",
            "rawDate": str(batch.preparation_date),
            "yieldQuantity": yield_qty,
            "yieldUnit": batch.yield_unit,
            "batchQty": f"{yield_qty} {batch.yield_unit}",
            "operator": batch.operator or "Chef",
            "status": batch.status,
            "totalCost": total_cost,
            "unitCost": unit_cost,
            "notes": batch.notes or "",
            "expiryDate": batch.expiry_date.strftime("%d %b %Y") if batch.expiry_date else "",
            "isStockDeducted": batch.is_stock_deducted,
            "rawMaterialsDeducted": summary,
            "ingredients": ingredients,
            "createdAt": batch.created_at.isoformat() if batch.created_at else None,
        }

    @classmethod
    def list_batches(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = ProductionBatch.objects.filter(deleted_at__isnull=True).select_related("recipe").prefetch_related(
            "ingredients_consumed__stock_item"
        )
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if status and status.upper() != "ALL":
            qs = qs.filter(status=status.upper())
        if search:
            qs = qs.filter(batch_number__icontains=search) | qs.filter(recipe__name__icontains=search) | qs.filter(operator__icontains=search)

        batches = [cls.serialize_batch(b) for b in qs.order_by("-created_at")]

        if (
            not batches
            and not search
            and (not status or status.upper() == "ALL")
            and not property_id
            and not outlet_id
        ):
            batches = cls.get_default_seed_batches()

        return batches

    @classmethod
    @transaction.atomic
    def create_batch(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        recipe_id = data.get("recipe_id") or data.get("recipeId")
        if not recipe_id:
            raise ValidationError({"recipe_id": "Recipe ID is required."})

        recipe = ProductionRecipe.objects.filter(pk=recipe_id, deleted_at__isnull=True).prefetch_related(
            "ingredients__stock_item"
        ).first()
        if not recipe:
            raise ValidationError({"recipe": "Recipe not found."})

        yield_qty = Decimal(str(data.get("yield_quantity") or data.get("yieldQty") or recipe.expected_yield or 1))
        yield_unit = data.get("yield_unit") or data.get("yieldUnit") or recipe.output_unit
        operator = data.get("operator") or data.get("chef") or "Chef"
        status_val = (data.get("status") or "COMPLETED").upper()
        notes = data.get("notes") or ""
        property_id = data.get("property_id") or data.get("propertyId") or (recipe.property_id if recipe else None)
        tenant_id = data.get("tenant_id") or data.get("tenantId") or (recipe.tenant_id if recipe else None)
        outlet_id = data.get("outlet_id") or data.get("outletId") or (recipe.outlet_id if recipe else None)

        prep_date_raw = data.get("preparation_date") or data.get("date")
        if prep_date_raw:
            if isinstance(prep_date_raw, str):
                try:
                    prep_date = datetime.strptime(prep_date_raw[:10], "%Y-%m-%d").date()
                except ValueError:
                    prep_date = timezone.now().date()
            else:
                prep_date = prep_date_raw
        else:
            prep_date = timezone.now().date()

        # Batch number
        batch_number = data.get("batch_number") or data.get("batchNumber")
        if not batch_number:
            today_str = prep_date.strftime("%Y%m%d")
            count = ProductionBatch.objects.filter(batch_number__startswith=f"PRD-{today_str}").count() + 1
            batch_number = f"PRD-{today_str}-{count:03d}"

        batch = ProductionBatch.objects.create(
            tenant_id=tenant_id,
            property_id=property_id,
            outlet_id=outlet_id,
            batch_number=batch_number,
            recipe=recipe,
            preparation_date=prep_date,
            yield_quantity=yield_qty,
            yield_unit=yield_unit,
            operator=operator,
            status=status_val,
            notes=notes,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        # Scale ingredients
        recipe_yield = Decimal(str(recipe.expected_yield or 1))
        scale_ratio = (yield_qty / recipe_yield) if recipe_yield > 0 else Decimal("1")

        raw_consumed = data.get("ingredients") or []
        consumed_map = {}
        for c in raw_consumed:
            s_id = str(c.get("stock_item_id") or c.get("stockItemId"))
            consumed_map[s_id] = Decimal(str(c.get("actual_quantity") or c.get("actualQuantity") or 0))

        total_cost = Decimal("0")
        for line in recipe.ingredients.all():
            std_qty = (line.quantity * scale_ratio).quantize(Decimal("0.001"))
            actual_qty = consumed_map.get(str(line.stock_item_id), std_qty)
            u_cost = line.unit_cost or line.stock_item.unit_cost or Decimal("0")
            line_total = (actual_qty * u_cost).quantize(Decimal("0.01"))
            total_cost += line_total

            ProductionBatchIngredient.objects.create(
                batch=batch,
                stock_item=line.stock_item,
                standard_quantity=std_qty,
                actual_quantity=actual_qty,
                unit=line.unit or line.stock_item.unit,
                unit_cost=u_cost,
                total_cost=line_total,
            )

        batch.total_cost = total_cost
        batch.save(update_fields=["total_cost", "updated_at"])

        if status_val == "COMPLETED":
            settings = StockService.get_inventory_settings(outlet_id)
            allow_negative = str(settings.get("restrictNegativeStockProduction", "Yes")).lower() not in ("yes", "true", "1")
            cls._deduct_batch_stock(batch, user=user, allow_negative=allow_negative)

        return cls.serialize_batch(batch)

    @classmethod
    @transaction.atomic
    def _deduct_batch_stock(cls, batch: ProductionBatch, user=None, allow_negative: bool = False):
        if batch.is_stock_deducted:
            return

        for ing in batch.ingredients_consumed.select_related("stock_item"):
            need = ing.actual_quantity
            if need > 0:
                StockService.adjust_stock(
                    ing.stock_item_id,
                    quantity=need,
                    movement_type="OUT",
                    notes=f"Food prep batch {batch.batch_number} · {batch.recipe.name}",
                    reference_type="PRODUCTION_BATCH",
                    reference_id=batch.id,
                    user=user,
                    allow_negative=allow_negative,
                )

        # If recipe has output stock item, increment its stock!
        if batch.recipe and batch.recipe.output_stock_item_id and batch.yield_quantity > 0:
            StockService.adjust_stock(
                batch.recipe.output_stock_item_id,
                quantity=batch.yield_quantity,
                movement_type="IN",
                notes=f"Produced from batch {batch.batch_number}",
                reference_type="PRODUCTION_BATCH",
                reference_id=batch.id,
                user=user,
            )

        batch.is_stock_deducted = True
        batch.save(update_fields=["is_stock_deducted", "updated_at"])

    @classmethod
    @transaction.atomic
    def update_batch_status(cls, batch_id, status: str, user=None) -> dict[str, Any]:
        batch = ProductionBatch.objects.filter(pk=batch_id, deleted_at__isnull=True).first()
        if not batch:
            raise ValidationError({"batch": "Batch not found."})
        status_val = status.upper()
        old_status = batch.status
        batch.status = status_val
        batch.save(update_fields=["status", "updated_at"])

        if status_val == "COMPLETED" and not batch.is_stock_deducted:
            settings = StockService.get_inventory_settings(batch.outlet_id)
            allow_negative = str(settings.get("restrictNegativeStockProduction", "Yes")).lower() not in ("yes", "true", "1")
            cls._deduct_batch_stock(batch, user=user, allow_negative=allow_negative)

        return cls.serialize_batch(batch)

    @classmethod
    def get_default_seed_recipes(cls) -> list[dict[str, Any]]:
        """Fallback rich mock data if DB empty."""
        return [
            {
                "id": "PRD-REC-01",
                "code": "PRD-REC-01",
                "name": "Makhani Gravy Base",
                "category": "Gravies & Sauces",
                "outputUnit": "Liter (L)",
                "expectedYield": 25,
                "standardCost": 1850,
                "costPerUnit": 74.0,
                "shelfLifeDays": 3,
                "instructions": "Slow simmer tomatoes with butter and cashew paste. Blend fine, strain, finish with fresh cream and kasoori methi.",
                "rawMaterialsCount": 5,
                "ingredientsSummary": "Fresh Tomatoes (15kg), Dairy Butter (3kg), Fresh Cream (2L), Cashew Nuts (1kg), Spices (500g)",
                "isActive": True,
                "ingredients": [
                    {"id": "ing-1", "stockItemId": "rm-1", "stockItemCode": "RM-TOMATO", "stockItemName": "Fresh Tomatoes", "quantity": 15, "unit": "kg", "unitCost": 40, "lineCost": 600},
                    {"id": "ing-2", "stockItemId": "rm-2", "stockItemCode": "RM-BUTTER", "stockItemName": "Dairy Butter", "quantity": 3, "unit": "kg", "unitCost": 280, "lineCost": 840},
                    {"id": "ing-3", "stockItemId": "rm-3", "stockItemCode": "RM-CREAM", "stockItemName": "Fresh Cream", "quantity": 2, "unit": "L", "unitCost": 160, "lineCost": 320},
                    {"id": "ing-4", "stockItemId": "rm-4", "stockItemCode": "RM-CASHEW", "stockItemName": "Cashew Nuts", "quantity": 1, "unit": "kg", "unitCost": 80, "lineCost": 80},
                    {"id": "ing-5", "stockItemId": "rm-5", "stockItemCode": "RM-SPICES", "stockItemName": "Makhani Spice Blend", "quantity": 0.5, "unit": "kg", "unitCost": 20, "lineCost": 10},
                ],
            },
            {
                "id": "PRD-REC-02",
                "code": "PRD-REC-02",
                "name": "Pizza Dough Balls (250g)",
                "category": "Bakery & Dough",
                "outputUnit": "Pieces (pcs)",
                "expectedYield": 40,
                "standardCost": 520,
                "costPerUnit": 13.0,
                "shelfLifeDays": 2,
                "instructions": "Hydrate active dry yeast in lukewarm water. Knead with high-protein 00 flour and olive oil. Proof at 4°C for 24h.",
                "rawMaterialsCount": 4,
                "ingredientsSummary": "Refined Flour 00 (10kg), Active Yeast (100g), Extra Virgin Olive Oil (500ml), Sea Salt (150g)",
                "isActive": True,
                "ingredients": [
                    {"id": "ing-6", "stockItemId": "rm-6", "stockItemCode": "RM-FLOUR", "stockItemName": "Refined Flour 00", "quantity": 10, "unit": "kg", "unitCost": 38, "lineCost": 380},
                    {"id": "ing-7", "stockItemId": "rm-7", "stockItemCode": "RM-YEAST", "stockItemName": "Active Dry Yeast", "quantity": 0.1, "unit": "kg", "unitCost": 400, "lineCost": 40},
                    {"id": "ing-8", "stockItemId": "rm-8", "stockItemCode": "RM-OLIVEOIL", "stockItemName": "Olive Oil", "quantity": 0.5, "unit": "L", "unitCost": 160, "lineCost": 80},
                    {"id": "ing-9", "stockItemId": "rm-9", "stockItemCode": "RM-SALT", "stockItemName": "Sea Salt", "quantity": 0.15, "unit": "kg", "unitCost": 133, "lineCost": 20},
                ],
            },
            {
                "id": "PRD-REC-03",
                "code": "PRD-REC-03",
                "name": "Tandoori Chicken Marination",
                "category": "Meat Marinations",
                "outputUnit": "Kilogram (kg)",
                "expectedYield": 15,
                "standardCost": 3100,
                "costPerUnit": 206.67,
                "shelfLifeDays": 4,
                "instructions": "First marination with lemon and salt for 30m. Second marination with hung curd, kashmiri chilli paste, mustard oil and garam masala.",
                "rawMaterialsCount": 4,
                "ingredientsSummary": "Fresh Chicken (15kg), Hung Curd (2.5kg), Mustard Oil (500ml), Tandoori Masala (400g)",
                "isActive": True,
                "ingredients": [
                    {"id": "ing-10", "stockItemId": "rm-10", "stockItemCode": "RM-CHICKEN", "stockItemName": "Fresh Chicken", "quantity": 15, "unit": "kg", "unitCost": 170, "lineCost": 2550},
                    {"id": "ing-11", "stockItemId": "rm-11", "stockItemCode": "RM-YOGURT", "stockItemName": "Hung Curd", "quantity": 2.5, "unit": "kg", "unitCost": 90, "lineCost": 225},
                    {"id": "ing-12", "stockItemId": "rm-12", "stockItemCode": "RM-MUSTARD", "stockItemName": "Mustard Oil", "quantity": 0.5, "unit": "L", "unitCost": 150, "lineCost": 75},
                    {"id": "ing-13", "stockItemId": "rm-13", "stockItemCode": "RM-TMASALA", "stockItemName": "Tandoori Masala", "quantity": 0.4, "unit": "kg", "unitCost": 625, "lineCost": 250},
                ],
            },
            {
                "id": "PRD-REC-04",
                "code": "PRD-REC-04",
                "name": "Brown Onion Gravy Base (Bhuna)",
                "category": "Gravies & Sauces",
                "outputUnit": "Liter (L)",
                "expectedYield": 20,
                "standardCost": 1420,
                "costPerUnit": 71.0,
                "shelfLifeDays": 3,
                "instructions": "Caramelize sliced red onions slowly until golden brown. Cook down with ginger-garlic paste and coriander-cumin powder.",
                "rawMaterialsCount": 4,
                "ingredientsSummary": "Red Onions (16kg), Refined Oil (3L), Ginger Garlic Paste (1.5kg), Whole Spices (300g)",
                "isActive": True,
                "ingredients": [
                    {"id": "ing-14", "stockItemId": "rm-14", "stockItemCode": "RM-ONION", "stockItemName": "Red Onions", "quantity": 16, "unit": "kg", "unitCost": 35, "lineCost": 560},
                    {"id": "ing-15", "stockItemId": "rm-15", "stockItemCode": "RM-REFOIL", "stockItemName": "Refined Oil", "quantity": 3, "unit": "L", "unitCost": 130, "lineCost": 390},
                    {"id": "ing-16", "stockItemId": "rm-16", "stockItemCode": "RM-GGPASTE", "stockItemName": "Ginger Garlic Paste", "quantity": 1.5, "unit": "kg", "unitCost": 180, "lineCost": 270},
                    {"id": "ing-17", "stockItemId": "rm-17", "stockItemCode": "RM-WSPICE", "stockItemName": "Whole Spices Blend", "quantity": 0.3, "unit": "kg", "unitCost": 666, "lineCost": 200},
                ],
            },
        ]

    @classmethod
    def get_default_seed_batches(cls) -> list[dict[str, Any]]:
        """Fallback rich mock batches."""
        return [
            {
                "id": "EXEC-881",
                "batchNumber": "PRD-20261017-001",
                "recipeId": "PRD-REC-01",
                "recipeName": "Makhani Gravy Base",
                "recipeCode": "PRD-REC-01",
                "category": "Gravies & Sauces",
                "preparationDate": "17 Oct 2026",
                "rawDate": "2026-10-17",
                "yieldQuantity": 25.0,
                "yieldUnit": "Liter (L)",
                "batchQty": "25 L",
                "operator": "Chef Vikram",
                "status": "COMPLETED",
                "totalCost": 1850.0,
                "unitCost": 74.0,
                "notes": "Color and consistency verified. Rich and smooth.",
                "expiryDate": "20 Oct 2026",
                "isStockDeducted": True,
                "rawMaterialsDeducted": "Fresh Tomatoes (15kg), Dairy Butter (3kg), Fresh Cream (2L)",
                "ingredients": [
                    {"id": "b-ing-1", "stockItemId": "rm-1", "stockItemCode": "RM-TOMATO", "stockItemName": "Fresh Tomatoes", "standardQuantity": 15, "actualQuantity": 15, "unit": "kg", "unitCost": 40, "totalCost": 600},
                    {"id": "b-ing-2", "stockItemId": "rm-2", "stockItemCode": "RM-BUTTER", "stockItemName": "Dairy Butter", "standardQuantity": 3, "actualQuantity": 3, "unit": "kg", "unitCost": 280, "totalCost": 840},
                    {"id": "b-ing-3", "stockItemId": "rm-3", "stockItemCode": "RM-CREAM", "stockItemName": "Fresh Cream", "standardQuantity": 2, "actualQuantity": 2, "unit": "L", "unitCost": 160, "totalCost": 320},
                ],
            },
            {
                "id": "EXEC-880",
                "batchNumber": "PRD-20261017-002",
                "recipeId": "PRD-REC-02",
                "recipeName": "Pizza Dough Balls (250g)",
                "recipeCode": "PRD-REC-02",
                "category": "Bakery & Dough",
                "preparationDate": "17 Oct 2026",
                "rawDate": "2026-10-17",
                "yieldQuantity": 40.0,
                "yieldUnit": "Pieces (pcs)",
                "batchQty": "40 pcs",
                "operator": "Sunita M.",
                "status": "IN_PROGRESS",
                "totalCost": 520.0,
                "unitCost": 13.0,
                "notes": "Fermenting in walk-in cold room. Target 24h rest.",
                "expiryDate": "19 Oct 2026",
                "isStockDeducted": False,
                "rawMaterialsDeducted": "Refined Flour 00 (10kg), Active Dry Yeast (100g)",
                "ingredients": [
                    {"id": "b-ing-4", "stockItemId": "rm-6", "stockItemCode": "RM-FLOUR", "stockItemName": "Refined Flour 00", "standardQuantity": 10, "actualQuantity": 10, "unit": "kg", "unitCost": 38, "totalCost": 380},
                    {"id": "b-ing-5", "stockItemId": "rm-7", "stockItemCode": "RM-YEAST", "stockItemName": "Active Dry Yeast", "standardQuantity": 0.1, "actualQuantity": 0.1, "unit": "kg", "unitCost": 400, "totalCost": 40},
                ],
            },
            {
                "id": "EXEC-879",
                "batchNumber": "PRD-20261016-003",
                "recipeId": "PRD-REC-03",
                "recipeName": "Tandoori Chicken Marination",
                "recipeCode": "PRD-REC-03",
                "category": "Meat Marinations",
                "preparationDate": "16 Oct 2026",
                "rawDate": "2026-10-16",
                "yieldQuantity": 15.0,
                "yieldUnit": "Kilogram (kg)",
                "batchQty": "15 kg",
                "operator": "Chef Vikram",
                "status": "COMPLETED",
                "totalCost": 3100.0,
                "unitCost": 206.67,
                "notes": "Quality check passed. Tenderized perfectly.",
                "expiryDate": "20 Oct 2026",
                "isStockDeducted": True,
                "rawMaterialsDeducted": "Fresh Chicken (15kg), Hung Curd (2.5kg), Mustard Oil (500ml)",
                "ingredients": [
                    {"id": "b-ing-6", "stockItemId": "rm-10", "stockItemCode": "RM-CHICKEN", "stockItemName": "Fresh Chicken", "standardQuantity": 15, "actualQuantity": 15, "unit": "kg", "unitCost": 170, "totalCost": 2550},
                    {"id": "b-ing-7", "stockItemId": "rm-11", "stockItemCode": "RM-YOGURT", "stockItemName": "Hung Curd", "standardQuantity": 2.5, "actualQuantity": 2.5, "unit": "kg", "unitCost": 90, "totalCost": 225},
                ],
            },
        ]
