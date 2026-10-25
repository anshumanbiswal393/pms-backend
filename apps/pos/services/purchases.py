"""
POS Unified Purchases Service.
Handles purchase bills, supplier accounts, incoming stock adjustments, and bill payments.
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
    POSVendor,
    POSPurchaseInvoice,
    POSPurchasePayment,
    POSPurchaseLine,
    POSPurchaseOrder,
    POSPurchaseOrderLine,
    POSPurchaseReturn,
    POSPurchaseReturnLine,
)
from apps.POS.services.stock import StockService


class PurchaseService:
    """Unified Purchase Service."""

    @classmethod
    def serialize_purchase(cls, p: POSPurchaseInvoice) -> dict[str, Any]:
        total = float(p.total_amount)
        paid = float(p.paid_amount)
        balance = float(p.balance_amount)

        # Map payment_status to user-friendly "Done" / "Pending" / "Partial"
        status_map = {
            "PAID": "Done",
            "UNPAID": "Pending",
            "PARTIAL": "Partial",
        }
        ui_payment_status = status_map.get(p.payment_status, "Done" if balance <= 0 else "Pending")

        payments = [
            {
                "id": str(pm.id),
                "amount": float(pm.amount),
                "paymentMethod": pm.payment_method,
                "paymentDate": pm.payment_date.strftime("%d %b %Y") if pm.payment_date else "",
                "referenceNo": pm.reference_no or "",
                "notes": pm.notes or "",
            }
            for pm in p.payments.all()
        ]

        lines = list(getattr(p, "lines", POSPurchaseLine.objects.none()).all()) if hasattr(p, "lines") else []
        items = [
            {
                "id": str(line.id),
                "stockItemId": str(line.stock_item_id) if line.stock_item_id else None,
                "name": line.name,
                "quantity": float(line.quantity),
                "unit": line.unit or "",
                "unitPrice": float(line.unit_price),
                "lineTotal": float(line.line_total),
            }
            for line in lines
        ] or (p.items_payload or [])

        return {
            "id": str(p.id),
            "invoiceNo": p.invoice_no,
            "vendorId": str(p.vendor_id) if p.vendor_id else None,
            "vendorName": p.vendor_name,
            "purchaseDate": p.purchase_date.strftime("%d %b %Y") if p.purchase_date else "",
            "invoiceDate": p.invoice_date.strftime("%d %b %Y") if p.invoice_date else "",
            "rawDate": str(p.invoice_date),
            "dueDate": p.due_date.strftime("%d %b %Y") if p.due_date else "",
            "totalAmount": total,
            "taxAmount": float(p.tax_amount),
            "paidAmount": paid,
            "balanceAmount": balance,
            "itemCount": p.item_count,
            "paymentStatus": ui_payment_status,
            "rawPaymentStatus": p.payment_status,
            "status": "Completed" if p.status == "COMPLETED" else p.status.capitalize(),
            "notes": p.notes or "",
            "items": items,
            "payments": payments,
            "createdAt": p.created_at.isoformat() if p.created_at else None,
        }

    @classmethod
    def list_purchases(
        cls,
        *,
        property_id=None,
        tenant_id=None,
        outlet_id=None,
        start_date: str | None = None,
        end_date: str | None = None,
        vendor: str | None = None,
        payment_status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = POSPurchaseInvoice.objects.filter(deleted_at__isnull=True).prefetch_related("payments", "lines")

        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)

        # Date range filtering
        if start_date:
            try:
                s_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
                qs = qs.filter(invoice_date__gte=s_dt)
            except ValueError:
                pass

        if end_date:
            try:
                e_dt = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
                qs = qs.filter(invoice_date__lte=e_dt)
            except ValueError:
                pass

        if vendor and vendor.lower() != "all":
            qs = qs.filter(vendor_name__icontains=vendor)

        if payment_status and payment_status.upper() != "ALL":
            p_val = payment_status.upper()
            if p_val == "DONE":
                p_val = "PAID"
            elif p_val == "PENDING":
                p_val = "UNPAID"
            qs = qs.filter(payment_status=p_val)

        if search:
            qs = qs.filter(invoice_no__icontains=search) | qs.filter(vendor_name__icontains=search)

        purchases = [cls.serialize_purchase(p) for p in qs.order_by("-purchase_date", "-created_at")]

        if (
            not purchases
            and not search
            and (not payment_status or payment_status.upper() == "ALL")
            and not vendor
            and not property_id
            and not outlet_id
        ):
            purchases = cls.get_default_seed_purchases()

        return purchases

    @classmethod
    @transaction.atomic
    def create_purchase(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        vendor_name = (data.get("vendorName") or data.get("vendor_name") or "Metro Cash & Carry").strip()
        invoice_no = (data.get("invoiceNo") or data.get("invoice_no") or "").strip()
        total_amount = Decimal(str(data.get("totalAmount") or data.get("total_amount") or 0))
        tax_amount = Decimal(str(data.get("taxAmount") or data.get("tax_amount") or 0))
        item_count = int(data.get("itemCount") or data.get("item_count") or 1)
        notes = data.get("notes") or ""
        items_payload = data.get("items") or []
        if not items_payload:
            raise ValidationError({"items": "At least one purchase line with quantity is required."})

        property_id = data.get("property_id") or data.get("propertyId")
        tenant_id = data.get("tenant_id") or data.get("tenantId")
        outlet_id = data.get("outlet_id") or data.get("outletId")

        if not invoice_no:
            today_str = timezone.now().strftime("%Y%m%d")
            count = POSPurchaseInvoice.objects.filter(invoice_no__startswith=f"INV-{today_str}").count() + 1
            invoice_no = f"INV-{today_str}-{count:03d}"

        raw_inv_date = data.get("invoiceDate") or data.get("invoice_date")
        if raw_inv_date:
            try:
                inv_date = datetime.strptime(str(raw_inv_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                inv_date = timezone.now().date()
        else:
            inv_date = timezone.now().date()

        # Payment status handling
        payment_status_input = (data.get("paymentStatus") or data.get("payment_status") or "PAID").upper()
        if payment_status_input in ("DONE", "PAID"):
            paid_amount = total_amount
            balance_amount = Decimal("0")
            db_payment_status = "PAID"
        elif payment_status_input in ("PENDING", "UNPAID"):
            paid_amount = Decimal("0")
            balance_amount = total_amount
            db_payment_status = "UNPAID"
        else: # PARTIAL
            initial_paid = Decimal(str(data.get("paidAmount") or data.get("paid_amount") or 0))
            paid_amount = min(initial_paid, total_amount)
            balance_amount = max(Decimal("0"), total_amount - paid_amount)
            db_payment_status = "PAID" if balance_amount <= 0 else "PARTIAL"

        invoice = POSPurchaseInvoice.objects.create(
            tenant_id=tenant_id,
            property_id=property_id,
            outlet_id=outlet_id,
            invoice_no=invoice_no,
            vendor_name=vendor_name,
            purchase_date=inv_date,
            invoice_date=inv_date,
            total_amount=total_amount,
            tax_amount=tax_amount,
            paid_amount=paid_amount,
            balance_amount=balance_amount,
            payment_status=db_payment_status,
            status="COMPLETED",
            item_count=item_count if item_count > 0 else (len(items_payload) or 1),
            notes=notes,
            items_payload=items_payload,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        # If payment made, record POSPurchasePayment
        if paid_amount > 0:
            payment_method = (data.get("paymentMethod") or data.get("payment_method") or "CASH").upper()
            POSPurchasePayment.objects.create(
                invoice=invoice,
                amount=paid_amount,
                payment_method=payment_method,
                payment_date=inv_date,
                reference_no=data.get("referenceNo") or invoice_no,
                notes=f"Initial payment for {invoice_no}",
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

        for it in items_payload:
            stock_id = it.get("stockItemId") or it.get("stock_item_id")
            qty = Decimal(str(it.get("quantity") or 0))
            name = (it.get("name") or "").strip()
            unit_price = Decimal(str(it.get("unitPrice") or it.get("unit_price") or 0))
            line_total = Decimal(str(it.get("lineTotal") or it.get("line_total") or (qty * unit_price)))
            unit = it.get("unit") or ""
            stock = None
            if stock_id:
                stock = POSStockItem.objects.filter(pk=stock_id, deleted_at__isnull=True).first()
                if stock and not name:
                    name = stock.name
                if stock and not unit:
                    unit = stock.unit
            POSPurchaseLine.objects.create(
                invoice=invoice,
                stock_item=stock,
                name=name or "Item",
                quantity=qty,
                unit=unit,
                unit_price=unit_price,
                tax=Decimal(str(it.get("tax") or 0)),
                line_total=line_total,
            )
            if stock and qty > 0:
                StockService.adjust_stock(
                    stock.id,
                    quantity=qty,
                    movement_type="IN",
                    notes=f"Purchase inward {invoice.invoice_no} · {vendor_name}",
                    reference_type="PURCHASE_INVOICE",
                    reference_id=invoice.id,
                    user=user,
                )

        return cls.serialize_purchase(invoice)

    @classmethod
    @transaction.atomic
    def record_payment(
        cls,
        invoice_id,
        *,
        amount: Decimal | float,
        payment_method: str = "CASH",
        reference_no: str = "",
        notes: str = "",
        user=None,
    ) -> dict[str, Any]:
        invoice = POSPurchaseInvoice.objects.filter(pk=invoice_id, deleted_at__isnull=True).first()
        if not invoice:
            raise ValidationError({"invoice": "Purchase invoice not found."})

        amt = Decimal(str(amount))
        if amt <= 0:
            raise ValidationError({"amount": "Payment amount must be greater than zero."})

        POSPurchasePayment.objects.create(
            invoice=invoice,
            amount=amt,
            payment_method=payment_method.upper(),
            payment_date=timezone.now().date(),
            reference_no=reference_no,
            notes=notes,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        new_paid = (Decimal(str(invoice.paid_amount)) + amt).quantize(Decimal("0.01"))
        total = Decimal(str(invoice.total_amount))
        new_balance = max(Decimal("0"), total - new_paid).quantize(Decimal("0.01"))

        invoice.paid_amount = new_paid
        invoice.balance_amount = new_balance
        if new_balance <= 0:
            invoice.payment_status = "PAID"
        else:
            invoice.payment_status = "PARTIAL"

        invoice.save(update_fields=["paid_amount", "balance_amount", "payment_status", "updated_at"])
        return cls.serialize_purchase(invoice)

    @classmethod
    @transaction.atomic
    def delete_purchase(cls, invoice_id, *, user=None) -> bool:
        invoice = POSPurchaseInvoice.objects.filter(pk=invoice_id, deleted_at__isnull=True).first()
        if not invoice:
            return False
        StockService.reverse_reference(
            reference_type="PURCHASE_INVOICE",
            reference_id=invoice.id,
            notes=f"Reverse purchase {invoice.invoice_no}",
            user=user,
        )
        invoice.deleted_at = timezone.now()
        invoice.status = "CANCELLED"
        invoice.save(update_fields=["deleted_at", "status", "updated_at"])
        return True

    @classmethod
    def get_default_seed_purchases(cls) -> list[dict[str, Any]]:
        return [
            {
                "id": "PUR-9042",
                "invoiceNo": "INV-20261017-001",
                "vendorName": "Metro Cash & Carry",
                "purchaseDate": "17 Oct 2026",
                "invoiceDate": "17 Oct 2026",
                "rawDate": "2026-10-17",
                "dueDate": "24 Oct 2026",
                "totalAmount": 18450.0,
                "taxAmount": 922.5,
                "paidAmount": 18450.0,
                "balanceAmount": 0.0,
                "itemCount": 6,
                "paymentStatus": "Done",
                "rawPaymentStatus": "PAID",
                "status": "Completed",
                "notes": "Bulk weekly staples & groceries received in good condition.",
                "items": [
                    {"name": "Basmati Biryani Rice (50kg)", "quantity": 2, "unit": "Bags", "unitPrice": 4500, "lineTotal": 9000},
                    {"name": "Refined Sunflower Oil (15L)", "quantity": 4, "unit": "Tins", "unitPrice": 1850, "lineTotal": 7400},
                    {"name": "Whole Spices Assorted", "quantity": 5, "unit": "kg", "unitPrice": 410, "lineTotal": 2050},
                ],
                "payments": [
                    {"id": "pm-1", "amount": 18450.0, "paymentMethod": "BANK_TRANSFER", "paymentDate": "17 Oct 2026", "referenceNo": "NEFT-991204", "notes": "Full settlement via HDFC NetBanking"}
                ],
            },
            {
                "id": "PUR-9041",
                "invoiceNo": "INV-20261017-002",
                "vendorName": "Royal Dairy Suppliers",
                "purchaseDate": "17 Oct 2026",
                "invoiceDate": "17 Oct 2026",
                "rawDate": "2026-10-17",
                "dueDate": "20 Oct 2026",
                "totalAmount": 8200.0,
                "taxAmount": 410.0,
                "paidAmount": 0.0,
                "balanceAmount": 8200.0,
                "itemCount": 4,
                "paymentStatus": "Pending",
                "rawPaymentStatus": "UNPAID",
                "status": "Completed",
                "notes": "Daily morning dairy delivery. Net 3 days credit terms.",
                "items": [
                    {"name": "Dairy Butter 500g Blocks", "quantity": 20, "unit": "pcs", "unitPrice": 240, "lineTotal": 4800},
                    {"name": "Fresh Paneer Malai", "quantity": 10, "unit": "kg", "unitPrice": 340, "lineTotal": 3400},
                ],
                "payments": [],
            },
            {
                "id": "PUR-9040",
                "invoiceNo": "INV-20261016-003",
                "vendorName": "Fresh Farm Greens & Veggies",
                "purchaseDate": "16 Oct 2026",
                "invoiceDate": "16 Oct 2026",
                "rawDate": "2026-10-16",
                "dueDate": "23 Oct 2026",
                "totalAmount": 12600.0,
                "taxAmount": 0.0,
                "paidAmount": 5000.0,
                "balanceAmount": 7600.0,
                "itemCount": 8,
                "paymentStatus": "Partial",
                "rawPaymentStatus": "PARTIAL",
                "status": "Completed",
                "notes": "Farm vegetables consignment. Advance ₹5,000 paid via UPI.",
                "items": [
                    {"name": "Nashik Red Onions", "quantity": 100, "unit": "kg", "unitPrice": 35, "lineTotal": 3500},
                    {"name": "Fresh Hybrid Tomatoes", "quantity": 80, "unit": "kg", "unitPrice": 40, "lineTotal": 3200},
                    {"name": "Potatoes Jyoti", "quantity": 120, "unit": "kg", "unitPrice": 28, "lineTotal": 3360},
                    {"name": "Ginger & Garlic Mixed", "quantity": 15, "unit": "kg", "unitPrice": 170, "lineTotal": 2540},
                ],
                "payments": [
                    {"id": "pm-2", "amount": 5000.0, "paymentMethod": "UPI", "paymentDate": "16 Oct 2026", "referenceNo": "UPI-REF-88741", "notes": "Advance payment"}
                ],
            },
            {
                "id": "PUR-9039",
                "invoiceNo": "INV-20261015-004",
                "vendorName": "Supreme Poultry & Meat",
                "purchaseDate": "15 Oct 2026",
                "invoiceDate": "15 Oct 2026",
                "rawDate": "2026-10-15",
                "dueDate": "15 Oct 2026",
                "totalAmount": 15500.0,
                "taxAmount": 0.0,
                "paidAmount": 15500.0,
                "balanceAmount": 0.0,
                "itemCount": 3,
                "paymentStatus": "Done",
                "rawPaymentStatus": "PAID",
                "status": "Completed",
                "notes": "Fresh boneless chicken & mutton cuts. Paid cash on delivery.",
                "items": [
                    {"name": "Boneless Chicken Breast", "quantity": 40, "unit": "kg", "unitPrice": 240, "lineTotal": 9600},
                    {"name": "Mutton Curry Cut", "quantity": 10, "unit": "kg", "unitPrice": 590, "lineTotal": 5900},
                ],
                "payments": [
                    {"id": "pm-3", "amount": 15500.0, "paymentMethod": "CASH", "paymentDate": "15 Oct 2026", "referenceNo": "CASH-RECEIPT", "notes": "Paid cash on delivery"}
                ],
            },
        ]

    @classmethod
    def serialize_vendor(cls, v: POSVendor) -> dict[str, Any]:
        return {
            "id": str(v.id),
            "name": v.name,
            "contactPerson": v.contact_person or "",
            "phone": v.phone or "",
            "email": v.email or "",
            "category": v.category or "General",
            "gstin": v.gstin or "",
            "address": v.address or "",
        }

    @classmethod
    def list_vendors(cls, *, property_id=None, tenant_id=None, search=None) -> list[dict[str, Any]]:
        qs = POSVendor.objects.filter(is_active=True)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if search:
            qs = qs.filter(name__icontains=search)
        if not qs.exists() and not search:
            cls._ensure_seed_vendors(property_id, tenant_id)
            qs = POSVendor.objects.filter(is_active=True)
        return [cls.serialize_vendor(v) for v in qs.order_by("name")]

    @classmethod
    def _ensure_seed_vendors(cls, property_id=None, tenant_id=None):
        if POSVendor.objects.filter(is_active=True).exists():
            return
        defaults = [
            {"name": "Metro Cash & Carry", "phone": "+91 98200 12345", "category": "Groceries & Dry Goods", "contact_person": "Vikram Patel"},
            {"name": "Royal Dairy Suppliers", "phone": "+91 98200 54321", "category": "Dairy & Milk", "contact_person": "Suresh Yadav"},
            {"name": "Fresh Farm Greens & Veggies", "phone": "+91 98300 11223", "category": "Fresh Produce", "contact_person": "Ramesh Kumar"},
            {"name": "Classic Spirits & Beverages", "phone": "+91 98400 99887", "category": "Beverages & Liquor", "contact_person": "Anand Shah"},
            {"name": "Supreme Poultry & Meat", "phone": "+91 98500 44556", "category": "Meat & Poultry", "contact_person": "Mohd. Aslam"},
        ]
        for d in defaults:
            POSVendor.objects.create(
                tenant_id=tenant_id,
                property_id=property_id,
                name=d["name"],
                phone=d["phone"],
                category=d["category"],
                contact_person=d.get("contact_person", ""),
                is_active=True,
            )

    @classmethod
    @transaction.atomic
    def create_vendor(cls, data: dict[str, Any], *, property_id=None, tenant_id=None, user=None) -> dict[str, Any]:
        name = (data.get("name") or data.get("vendorName") or "").strip()
        if not name:
            raise ValidationError({"name": "Vendor name is required."})

        contact_person = (data.get("contactPerson") or data.get("contact_person") or "").strip()
        phone = (data.get("phone") or "").strip()
        email = (data.get("email") or "").strip()
        category = (data.get("category") or "General").strip()
        gstin = (data.get("gstin") or "").strip()
        address = (data.get("address") or "").strip()

        # Check existing active vendor
        existing = POSVendor.objects.filter(name__iexact=name, is_active=True).first()
        if existing:
            if phone:
                existing.phone = phone
            if email:
                existing.email = email
            if contact_person:
                existing.contact_person = contact_person
            if category:
                existing.category = category
            if gstin:
                existing.gstin = gstin
            if address:
                existing.address = address
            existing.save()
            return cls.serialize_vendor(existing)

        vendor = POSVendor.objects.create(
            tenant_id=tenant_id or data.get("tenant_id") or data.get("tenantId"),
            property_id=property_id or data.get("property_id") or data.get("propertyId"),
            name=name,
            contact_person=contact_person,
            phone=phone,
            email=email or None,
            category=category,
            gstin=gstin,
            address=address,
            is_active=True,
        )
        return cls.serialize_vendor(vendor)

    @classmethod
    @transaction.atomic
    def delete_vendor(cls, vendor_id, *, user=None) -> bool:
        vendor = POSVendor.objects.filter(pk=vendor_id).first()
        if not vendor:
            return False
        vendor.is_active = False
        vendor.save(update_fields=["is_active"])
        return True

    @classmethod
    def _parse_date(cls, raw, fallback=None):
        if not raw:
            return fallback or timezone.now().date()
        try:
            return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            return fallback or timezone.now().date()

    @classmethod
    def serialize_purchase_order(cls, po: POSPurchaseOrder) -> dict[str, Any]:
        status_map = {
            "DRAFT": "Draft",
            "SENT": "Sent",
            "APPROVED": "Approved",
            "RECEIVED": "Received",
            "CANCELLED": "Cancelled",
        }
        items = [
            {
                "id": str(line.id),
                "stockItemId": str(line.stock_item_id) if line.stock_item_id else None,
                "name": line.name,
                "quantity": float(line.quantity),
                "unit": line.unit or "",
                "unitPrice": float(line.unit_price),
                "lineTotal": float(line.line_total),
            }
            for line in po.lines.all()
        ]
        return {
            "id": str(po.id),
            "poNumber": po.po_number,
            "vendorId": str(po.vendor_id) if po.vendor_id else None,
            "vendorName": po.vendor_name,
            "orderDate": po.order_date.strftime("%d %b %Y") if po.order_date else "",
            "expectedDeliveryDate": po.expected_delivery_date.strftime("%Y-%m-%d") if po.expected_delivery_date else "",
            "itemCount": po.item_count or len(items),
            "estimatedAmount": float(po.estimated_amount),
            "status": status_map.get(po.status, po.status.capitalize()),
            "notes": po.notes or "",
            "items": items,
            "receivedInvoiceId": str(po.received_invoice_id) if po.received_invoice_id else None,
        }

    @classmethod
    def list_purchase_orders(cls, *, property_id=None, tenant_id=None, outlet_id=None) -> list[dict[str, Any]]:
        qs = POSPurchaseOrder.objects.filter(deleted_at__isnull=True).prefetch_related("lines")
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return [cls.serialize_purchase_order(p) for p in qs.order_by("-order_date", "-created_at")]

    @classmethod
    @transaction.atomic
    def create_purchase_order(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        vendor_name = (data.get("vendorName") or data.get("vendor_name") or "").strip()
        if not vendor_name:
            raise ValidationError({"vendorName": "Vendor is required."})
        po_number = (data.get("poNumber") or data.get("po_number") or "").strip()
        if not po_number:
            today_str = timezone.now().strftime("%Y%m%d")
            count = POSPurchaseOrder.objects.filter(po_number__startswith=f"PO-{today_str}").count() + 1
            po_number = f"PO-{today_str}-{count:03d}"
        items_payload = data.get("items") or []
        status_in = (data.get("status") or "SENT").upper()
        if status_in in ("SENT", "DRAFT", "APPROVED"):
            db_status = status_in
        else:
            db_status = "SENT"
        po = POSPurchaseOrder.objects.create(
            tenant_id=data.get("tenant_id") or data.get("tenantId"),
            property_id=data.get("property_id") or data.get("propertyId"),
            outlet_id=data.get("outlet_id") or data.get("outletId"),
            po_number=po_number,
            vendor_name=vendor_name,
            order_date=cls._parse_date(data.get("orderDate") or data.get("order_date")),
            expected_delivery_date=cls._parse_date(
                data.get("expectedDeliveryDate") or data.get("expected_delivery_date"),
                fallback=None,
            ) if (data.get("expectedDeliveryDate") or data.get("expected_delivery_date")) else None,
            item_count=int(data.get("itemCount") or data.get("item_count") or len(items_payload) or 1),
            estimated_amount=Decimal(str(data.get("estimatedAmount") or data.get("estimated_amount") or 0)),
            status=db_status,
            notes=data.get("notes") or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        total = Decimal("0")
        for it in items_payload:
            qty = Decimal(str(it.get("quantity") or 0))
            price = Decimal(str(it.get("unitPrice") or it.get("unit_price") or 0))
            line_total = Decimal(str(it.get("lineTotal") or qty * price))
            total += line_total
            stock_id = it.get("stockItemId") or it.get("stock_item_id")
            POSPurchaseOrderLine.objects.create(
                purchase_order=po,
                stock_item_id=stock_id if stock_id else None,
                name=it.get("name") or "Item",
                quantity=qty,
                unit=it.get("unit") or "",
                unit_price=price,
                line_total=line_total,
            )
        if items_payload:
            po.estimated_amount = total
            po.item_count = len(items_payload)
            po.save(update_fields=["estimated_amount", "item_count", "updated_at"])
        return cls.serialize_purchase_order(po)

    @classmethod
    def delete_purchase_order(cls, pk) -> bool:
        po = POSPurchaseOrder.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not po:
            return False
        if po.status == "RECEIVED":
            raise ValidationError({"purchase_order": "Received purchase orders cannot be deleted."})
        po.deleted_at = timezone.now()
        po.status = "CANCELLED"
        po.save(update_fields=["deleted_at", "status", "updated_at"])
        return True

    @classmethod
    @transaction.atomic
    def receive_purchase_order(cls, pk, *, user=None) -> dict[str, Any]:
        po = POSPurchaseOrder.objects.filter(pk=pk, deleted_at__isnull=True).prefetch_related("lines").first()
        if not po:
            raise ValidationError({"purchase_order": "Purchase order not found."})
        if po.status == "RECEIVED":
            raise ValidationError({"purchase_order": "Already received."})
        items = [
            {
                "stockItemId": str(line.stock_item_id) if line.stock_item_id else None,
                "name": line.name,
                "quantity": float(line.quantity),
                "unit": line.unit,
                "unitPrice": float(line.unit_price),
                "lineTotal": float(line.line_total),
            }
            for line in po.lines.all()
        ]
        if not items:
            items = [{"name": "PO receipt", "quantity": 1, "unit": "lot", "unitPrice": float(po.estimated_amount), "lineTotal": float(po.estimated_amount)}]
        invoice = cls.create_purchase(
            {
                "vendorName": po.vendor_name,
                "invoiceNo": f"GRN-{po.po_number}",
                "totalAmount": float(po.estimated_amount),
                "taxAmount": 0,
                "paymentStatus": "UNPAID",
                "notes": f"Received from {po.po_number}",
                "items": items,
                "property_id": po.property_id,
                "tenant_id": po.tenant_id,
                "outlet_id": po.outlet_id,
            },
            user=user,
        )
        po.status = "RECEIVED"
        po.received_invoice_id = invoice["id"]
        po.save(update_fields=["status", "received_invoice_id", "updated_at"])
        payload = cls.serialize_purchase_order(po)
        payload["invoice"] = invoice
        return payload

    @classmethod
    def serialize_purchase_return(cls, row: POSPurchaseReturn) -> dict[str, Any]:
        items = [
            {
                "id": str(line.id),
                "stockItemId": str(line.stock_item_id) if line.stock_item_id else None,
                "name": line.name,
                "quantity": float(line.quantity),
                "unit": line.unit or "",
                "unitPrice": float(line.unit_price),
                "lineTotal": float(line.line_total),
            }
            for line in row.lines.all()
        ]
        return {
            "id": str(row.id),
            "debitNoteNo": row.debit_note_no,
            "vendorId": str(row.vendor_id) if row.vendor_id else None,
            "vendorName": row.vendor_name,
            "returnDate": row.return_date.strftime("%d %b %Y") if row.return_date else "",
            "reason": row.reason,
            "itemCount": row.item_count or len(items),
            "returnAmount": float(row.return_amount),
            "status": row.status.capitalize() if row.status != "ISSUED" else "Issued",
            "notes": row.notes or "",
            "items": items,
        }

    @classmethod
    def list_purchase_returns(cls, *, property_id=None, tenant_id=None, outlet_id=None) -> list[dict[str, Any]]:
        qs = POSPurchaseReturn.objects.filter(deleted_at__isnull=True).prefetch_related("lines")
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return [cls.serialize_purchase_return(r) for r in qs.order_by("-return_date", "-created_at")]

    @classmethod
    @transaction.atomic
    def create_purchase_return(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        vendor_name = (data.get("vendorName") or data.get("vendor_name") or "").strip()
        if not vendor_name:
            raise ValidationError({"vendorName": "Vendor is required."})
        debit = (data.get("debitNoteNo") or data.get("debit_note_no") or "").strip()
        if not debit:
            today_str = timezone.now().strftime("%Y%m%d")
            count = POSPurchaseReturn.objects.filter(debit_note_no__startswith=f"DN-{today_str}").count() + 1
            debit = f"DN-{today_str}-{count:03d}"
        items_payload = data.get("items") or []
        row = POSPurchaseReturn.objects.create(
            tenant_id=data.get("tenant_id") or data.get("tenantId"),
            property_id=data.get("property_id") or data.get("propertyId"),
            outlet_id=data.get("outlet_id") or data.get("outletId"),
            debit_note_no=debit,
            vendor_name=vendor_name,
            return_date=cls._parse_date(data.get("returnDate") or data.get("return_date")),
            reason=data.get("reason") or "Damaged / Expired",
            item_count=int(data.get("itemCount") or data.get("item_count") or len(items_payload) or 1),
            return_amount=Decimal(str(data.get("returnAmount") or data.get("return_amount") or 0)),
            status="ISSUED",
            notes=data.get("notes") or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        deducted = False
        total = Decimal("0")
        for it in items_payload:
            qty = Decimal(str(it.get("quantity") or 0))
            price = Decimal(str(it.get("unitPrice") or it.get("unit_price") or 0))
            line_total = Decimal(str(it.get("lineTotal") or qty * price))
            total += line_total
            stock_id = it.get("stockItemId") or it.get("stock_item_id")
            POSPurchaseReturnLine.objects.create(
                purchase_return=row,
                stock_item_id=stock_id if stock_id else None,
                name=it.get("name") or "Item",
                quantity=qty,
                unit=it.get("unit") or "",
                unit_price=price,
                line_total=line_total,
            )
            if stock_id and qty > 0:
                StockService.adjust_stock(
                    stock_id,
                    quantity=qty,
                    movement_type="PURCHASE_RETURN",
                    notes=f"Purchase return {row.debit_note_no}",
                    reference_type="PURCHASE_RETURN",
                    reference_id=row.id,
                    user=user,
                )
                deducted = True
        if items_payload:
            row.return_amount = total
            row.item_count = len(items_payload)
        row.is_stock_reversed = deducted
        row.save(update_fields=["return_amount", "item_count", "is_stock_reversed", "updated_at"])
        return cls.serialize_purchase_return(row)

    @classmethod
    @transaction.atomic
    def delete_purchase_return(cls, pk, *, user=None) -> bool:
        row = POSPurchaseReturn.objects.filter(pk=pk, deleted_at__isnull=True).first()
        if not row:
            return False
        if row.is_stock_reversed:
            StockService.reverse_reference(
                reference_type="PURCHASE_RETURN",
                reference_id=row.id,
                notes=f"Cancel debit note {row.debit_note_no}",
                user=user,
            )
        row.deleted_at = timezone.now()
        row.status = "CANCELLED"
        row.save(update_fields=["deleted_at", "status", "updated_at"])
        return True

