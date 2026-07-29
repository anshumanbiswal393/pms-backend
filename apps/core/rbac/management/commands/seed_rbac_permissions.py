from django.core.management.base import BaseCommand
from apps.core.rbac.models import Permission, Role, RolePermission

class Command(BaseCommand):
    help = 'Seeds all system RBAC permissions and default global roles.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding RBAC Permissions Catalog...")

        # Definition of all system permissions by category
        PERMISSIONS_CATALOG = [
            # Reservations & Front Office
            {"category": "Reservations", "code": "reservations:view"},
            {"category": "Reservations", "code": "reservations:create"},
            {"category": "Reservations", "code": "reservations:update"},
            {"category": "Reservations", "code": "reservations:cancel"},
            {"category": "Reservations", "code": "reservations:checkin"},
            {"category": "Reservations", "code": "reservations:checkout"},

            # Rooms & Inventory
            {"category": "Inventory", "code": "inventory:view"},
            {"category": "Inventory", "code": "inventory:manage"},
            {"category": "Inventory", "code": "inventory:layout"},
            {"category": "Inventory", "code": "inventory:status"},

            # Rates & Pricing Strategies
            {"category": "Rates", "code": "rates:view"},
            {"category": "Rates", "code": "rates:manage"},
            {"category": "Rates", "code": "rates:packages"},

            # Services & Add-Ons Catalog
            {"category": "Services", "code": "services:view"},
            {"category": "Services", "code": "services:manage"},

            # Billing & Invoicing
            {"category": "Billing", "code": "billing:view"},
            {"category": "Billing", "code": "billing:post"},
            {"category": "Billing", "code": "billing:settle"},
            {"category": "Billing", "code": "billing:refund"},

            # Housekeeping & Maintenance
            {"category": "Housekeeping", "code": "housekeeping:view"},
            {"category": "Housekeeping", "code": "housekeeping:assign"},
            {"category": "Housekeeping", "code": "housekeeping:status"},
            {"category": "Housekeeping", "code": "maintenance:view"},
            {"category": "Housekeeping", "code": "maintenance:manage"},

            # CRM & Guests
            {"category": "CRM", "code": "crm:view"},
            {"category": "CRM", "code": "crm:manage"},

            # Channels & OTAs
            {"category": "Channels", "code": "channels:view"},
            {"category": "Channels", "code": "channels:manage"},

            # Analytics & Reports
            {"category": "Reports", "code": "reports:view"},
            {"category": "Reports", "code": "reports:export"},

            # System & Administration
            {"category": "Settings", "code": "settings:view"},
            {"category": "Settings", "code": "settings:manage"},
            {"category": "Settings", "code": "users:view"},
            {"category": "Settings", "code": "users:manage"},
        ]

        permission_objs = {}
        for item in PERMISSIONS_CATALOG:
            perm, created = Permission.objects.update_or_create(
                code=item["code"],
                defaults={"category": item["category"]}
            )
            permission_objs[item["code"]] = perm

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(permission_objs)} permissions."))

        # Global Roles Definition
        ROLES_CATALOG = [
            {
                "code": "super_admin",
                "name": "Super Admin",
                "description": "Full master developer control over all platform modules and tenants.",
                "permissions": list(permission_objs.keys()) # ALL
            },
            {
                "code": "owner",
                "name": "Owner",
                "description": "Full property group management and operational control.",
                "permissions": list(permission_objs.keys()) # ALL
            },
            {
                "code": "general_manager",
                "name": "General Manager",
                "description": "Full property local operations management.",
                "permissions": [
                    "reservations:view", "reservations:create", "reservations:update", "reservations:cancel", "reservations:checkin", "reservations:checkout",
                    "inventory:view", "inventory:manage", "inventory:layout", "inventory:status",
                    "rates:view", "rates:manage", "rates:packages",
                    "services:view", "services:manage",
                    "billing:view", "billing:post", "billing:settle", "billing:refund",
                    "housekeeping:view", "housekeeping:assign", "housekeeping:status", "maintenance:view", "maintenance:manage",
                    "crm:view", "crm:manage",
                    "channels:view", "channels:manage",
                    "reports:view", "reports:export",
                    "settings:view", "users:view"
                ]
            },
            {
                "code": "front_office_manager",
                "name": "Front Office Manager",
                "description": "Front desk oversight, check-ins, check-outs, and guest folios.",
                "permissions": [
                    "reservations:view", "reservations:create", "reservations:update", "reservations:cancel", "reservations:checkin", "reservations:checkout",
                    "inventory:view", "inventory:status",
                    "rates:view", "services:view",
                    "billing:view", "billing:post", "billing:settle", "billing:refund",
                    "crm:view", "crm:manage",
                    "reports:view"
                ]
            },
            {
                "code": "front_desk_agent",
                "name": "Front Desk Agent",
                "description": "Front office check-in/check-out transactions and folio billing.",
                "permissions": [
                    "reservations:view", "reservations:create", "reservations:update", "reservations:checkin", "reservations:checkout",
                    "inventory:view",
                    "billing:view", "billing:post", "billing:settle",
                    "crm:view", "crm:manage"
                ]
            },
            {
                "code": "housekeeping_supervisor",
                "name": "Housekeeping Supervisor",
                "description": "Room status coordination and maintenance task assignment.",
                "permissions": [
                    "inventory:view", "inventory:status",
                    "housekeeping:view", "housekeeping:assign", "housekeeping:status",
                    "maintenance:view", "maintenance:manage"
                ]
            },
            {
                "code": "accounts",
                "name": "Accounts",
                "description": "Invoices and balance settlement processing.",
                "permissions": [
                    "billing:view", "billing:post", "billing:settle", "billing:refund",
                    "rates:view", "services:view",
                    "reports:view", "reports:export"
                ]
            }
        ]

        role_count = 0
        role_perm_count = 0

        for r_data in ROLES_CATALOG:
            role, _ = Role.objects.update_or_create(
                tenant=None, # Global system role
                code=r_data["code"],
                defaults={
                    "name": r_data["name"],
                    "description": r_data["description"]
                }
            )
            role_count += 1

            # Map permissions
            for p_code in r_data["permissions"]:
                if p_code in permission_objs:
                    _, created = RolePermission.objects.get_or_create(
                        role=role,
                        permission=permission_objs[p_code]
                    )
                    if created:
                        role_perm_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {role_count} global roles with {role_perm_count} role-permission mappings!"
        ))
