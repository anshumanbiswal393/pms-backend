"""
Seed Part 2 POS menu catalog into the shared PMS PostgreSQL database.

Usage:
  python manage.py seed_pos_menu
  python manage.py seed_pos_menu --outlet-code MAIN --reset
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.POS.models import (
    Outlet,
    TaxProfile,
    MenuCategory,
    MenuItem,
    MenuVariant,
    SpecialNote,
)
from apps.POS.services.menu import MenuCatalogService
from apps.core.tenants.models import Tenant, Property


SEED_CATEGORIES = [
    ("STARTERS", "Starters", 1),
    ("MAINS", "Main Course", 2),
    ("BREADS", "Breads & Rice", 3),
    ("CONTINENTAL", "Continental & Pasta", 4),
    ("DESSERTS", "Desserts", 5),
    ("BEVERAGES", "Beverages & Shakes", 6),
    ("BAR", "Bar & Cocktails", 7),
    ("COMBOS", "Combos", 8),
]

# code, name, category_code, item_type, price, tax_rate, description, variants
SEED_ITEMS = [
    (
        "#101",
        "Paneer Tikka Angara",
        "STARTERS",
        "VEG",
        Decimal("340"),
        Decimal("5"),
        "Charcoal smoked cottage cheese marinated in fiery spices & hung curd",
        [("Half", Decimal("220")), ("Full", Decimal("340"))],
    ),
    (
        "#102",
        "Murgh Malai Tikka",
        "STARTERS",
        "NON_VEG",
        Decimal("420"),
        Decimal("5"),
        "Tender chicken chunks marinated in cream, cardamom, cashew paste & grilled",
        [("Half", Decimal("260")), ("Full", Decimal("420"))],
    ),
    (
        "#103",
        "Crispy Corn & Water Chestnut",
        "STARTERS",
        "VEG",
        Decimal("290"),
        Decimal("5"),
        "Golden fried sweet corn kernels tossed with crushed pepper, scallions and lime",
        [],
    ),
    (
        "#105",
        "Butter Chicken (Grandma Recipe)",
        "MAINS",
        "NON_VEG",
        Decimal("520"),
        Decimal("5"),
        "Smoked tandoori chicken cooked in velvety tomato, makhani gravy and cashew paste",
        [("Classic", Decimal("520")), ("Boneless", Decimal("560"))],
    ),
    (
        "#106",
        "Dal Makhani 24-Hour Slow Cooked",
        "MAINS",
        "VEG",
        Decimal("360"),
        Decimal("5"),
        "Black lentils simmered overnight with cream, butter and sun-dried fenugreek",
        [],
    ),
    (
        "#107",
        "Paneer Lababdar",
        "MAINS",
        "VEG",
        Decimal("410"),
        Decimal("5"),
        "Cottage cheese cubes bathed in rich onion tomato gravy with grated paneer",
        [],
    ),
    (
        "#109",
        "Garlic Butter Naan",
        "BREADS",
        "VEG",
        Decimal("95"),
        Decimal("5"),
        "Refined flour flatbread brushed with garlic butter and fresh coriander",
        [],
    ),
    (
        "#111",
        "Dum Awadhi Gosht Biryani",
        "BREADS",
        "NON_VEG",
        Decimal("580"),
        Decimal("5"),
        "Long grain basmati sealed in dough pot with tender lamb cuts, saffron & spices",
        [],
    ),
    (
        "#115",
        "Shahi Tukda with Saffron Rabri",
        "DESSERTS",
        "VEG",
        Decimal("210"),
        Decimal("5"),
        "Royal bread pudding with saffron rabri",
        [],
    ),
    (
        "#117",
        "Fresh Lime Soda (Sweet & Salt)",
        "BEVERAGES",
        "VEG",
        Decimal("140"),
        Decimal("12"),
        "Chilled fresh lime soda",
        [],
    ),
    (
        "#118",
        "Signature Berry Mojito",
        "BEVERAGES",
        "VEG",
        Decimal("220"),
        Decimal("12"),
        "Signature berry mojito sparkler",
        [],
    ),
    (
        "#120",
        "Smoked Old Fashioned Cocktail",
        "BAR",
        "VEG",
        Decimal("540"),
        Decimal("18"),
        "Craft smoked old fashioned",
        [],
    ),
    (
        "#122",
        "Royal Non-Veg Platter Combo",
        "COMBOS",
        "NON_VEG",
        Decimal("790"),
        Decimal("5"),
        "Assorted tandoori murgh, mutton seekh, fish tikka and butter naan",
        [],
    ),
]

SPECIAL_NOTES = [
    "Parcel",
    "Non Spice",
    "Spice",
    "More Spice",
    "No Onion No Garlic",
    "Jain Preparation",
    "Extra Dip & Cutlery",
]


class Command(BaseCommand):
    help = "Seed POS menu categories, tax profiles, and items into PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--outlet-code",
            default=None,
            help="Outlet code to seed (default: first active outlet for property).",
        )
        parser.add_argument(
            "--property-id",
            default=None,
            help="Property UUID (optional filter).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Soft-delete existing seeded items/categories for this outlet first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        outlet = self._resolve_outlet(options.get("outlet_code"), options.get("property_id"))
        self.stdout.write(f"Seeding menu for outlet {outlet.code} ({outlet.id}) …")

        if options["reset"]:
            MenuItem.objects.filter(outlet=outlet).delete()
            MenuCategory.objects.filter(outlet=outlet).delete()
            SpecialNote.objects.filter(outlet=outlet).delete()
            self.stdout.write(self.style.WARNING("Reset existing menu rows for outlet."))

        categories = {}
        for code, name, sort_order in SEED_CATEGORIES:
            cat, _ = MenuCategory.objects.get_or_create(
                outlet=outlet,
                name=name,
                defaults={
                    "code": code,
                    "online_display_name": name,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            if not cat.code:
                cat.code = code
                cat.save(update_fields=["code", "updated_at"])
            categories[code] = cat

        tax_cache = {}
        created_items = 0
        for (
            code,
            name,
            cat_code,
            item_type,
            price,
            tax_rate,
            description,
            variants,
        ) in SEED_ITEMS:
            if tax_rate not in tax_cache:
                tax_cache[tax_rate] = MenuCatalogService.resolve_or_create_tax_profile(
                    tenant_id=outlet.tenant_id,
                    property_id=outlet.property_id,
                    rate=tax_rate,
                )
            item, was_created = MenuItem.objects.get_or_create(
                outlet=outlet,
                code=code,
                defaults={
                    "category": categories[cat_code],
                    "tax_profile": tax_cache[tax_rate],
                    "name": name,
                    "online_display_name": name,
                    "item_type": item_type,
                    "price": price,
                    "description": description,
                    "status": "ACTIVE",
                    "base_menu": True,
                    "zomato": cat_code != "BAR",
                    "swiggy": cat_code != "BAR",
                    "direct": cat_code != "BAR",
                    "images": [],
                },
            )
            if was_created:
                created_items += 1
                for idx, (vname, vprice) in enumerate(variants):
                    MenuVariant.objects.create(
                        menu_item=item,
                        name=vname,
                        price=vprice,
                        sort_order=idx,
                        is_active=True,
                    )

        for idx, note_name in enumerate(SPECIAL_NOTES):
            SpecialNote.objects.get_or_create(
                outlet=outlet,
                name=note_name,
                defaults={
                    "tenant_id": outlet.tenant_id,
                    "is_available": True,
                    "sort_order": idx,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Categories={len(categories)} new_items={created_items} "
                f"tax_profiles={len(tax_cache)}"
            )
        )

    def _resolve_outlet(self, outlet_code, property_id):
        qs = Outlet.objects.filter(deleted_at__isnull=True, is_active=True)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_code:
            outlet = qs.filter(code__iexact=outlet_code).first()
            if not outlet:
                raise CommandError(f"No outlet with code={outlet_code}")
            return outlet

        outlet = qs.order_by("created_at").first()
        if outlet:
            return outlet

        # Bootstrap a minimal outlet if none exists
        tenant = Tenant.objects.first()
        prop = None
        if property_id:
            prop = Property.objects.filter(id=property_id).first()
        if not prop:
            prop = Property.objects.filter(tenant=tenant).first() if tenant else None
        if not tenant or not prop:
            raise CommandError(
                "No Outlet and no Tenant/Property found. Create them in PMS first."
            )
        outlet = Outlet.objects.create(
            tenant=tenant,
            property=prop,
            code="MAIN",
            name="Main Restaurant",
            outlet_type="PRIMARY",
            is_active=True,
        )
        self.stdout.write(self.style.WARNING(f"Created outlet MAIN ({outlet.id})"))
        return outlet
