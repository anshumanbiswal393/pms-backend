from django.core.management.base import BaseCommand
from apps.core.rbac.models import Permission, Role, RolePermission

class Command(BaseCommand):
    help = 'Seeds all system RBAC permissions and default global roles.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding RBAC Permissions Catalog...")

        # Definition of all system permissions by category with descriptions
        PERMISSIONS_CATALOG = [
            # Reservations & Front Office
            {"category": "Reservations", "code": "reservations:view", "description": "View reservation calendar, timeline, and booking details"},
            {"category": "Reservations", "code": "reservations:create", "description": "Create new reservations and group blocks"},
            {"category": "Reservations", "code": "reservations:update", "description": "Edit guest details, room assignments, and stay dates"},
            {"category": "Reservations", "code": "reservations:cancel", "description": "Cancel active bookings and process cancellation policies"},
            {"category": "Reservations", "code": "reservations:checkin", "description": "Process guest check-in and key card issuance"},
            {"category": "Reservations", "code": "reservations:checkout", "description": "Process guest check-out and folio settlement"},

            # Rooms & Inventory
            {"category": "Inventory", "code": "inventory:view", "description": "View room status, unit types, and floor plans"},
            {"category": "Inventory", "code": "inventory:manage", "description": "Create and edit unit types, room amenities, and room attributes"},
            {"category": "Inventory", "code": "inventory:layout", "description": "Configure building layouts, floor maps, and unit matrices"},
            {"category": "Inventory", "code": "inventory:status", "description": "Update out-of-order and out-of-service room statuses"},

            # Rates & Pricing Strategies
            {"category": "Rates", "code": "rates:view", "description": "View rate plans, seasonal pricing, and occupancy multipliers"},
            {"category": "Rates", "code": "rates:manage", "description": "Configure rate plans, rate rules, and dynamic pricing rules"},
            {"category": "Rates", "code": "rates:packages", "description": "Configure hospitality packages and meal plan pricing"},

            # Services & Add-Ons Catalog
            {"category": "Services", "code": "services:view", "description": "View extra service offerings and amenity catalog"},
            {"category": "Services", "code": "services:manage", "description": "Create and edit additional guest services and service categories"},

            # Billing & Invoicing
            {"category": "Billing", "code": "billing:view", "description": "View guest folios, invoices, and payment receipts"},
            {"category": "Billing", "code": "billing:post", "description": "Post custom charges, room charges, and minibar fees"},
            {"category": "Billing", "code": "billing:settle", "description": "Settle guest folios and accept payments"},
            {"category": "Billing", "code": "billing:refund", "description": "Process payment refunds and billing adjustments"},

            # Housekeeping & Maintenance
            {"category": "Housekeeping", "code": "housekeeping:view", "description": "View housekeeping tasks, linen assignments, and room cleaning statuses"},
            {"category": "Housekeeping", "code": "housekeeping:assign", "description": "Assign housekeepers to rooms and deep cleaning schedules"},
            {"category": "Housekeeping", "code": "housekeeping:status", "description": "Update room cleaning and inspection status"},
            {"category": "Housekeeping", "code": "maintenance:view", "description": "View maintenance tickets and asset issues"},
            {"category": "Housekeeping", "code": "maintenance:manage", "description": "Create and manage maintenance tickets and asset repairs"},

            # CRM & Guests
            {"category": "CRM", "code": "crm:view", "description": "View guest profiles, stay history, and contact details"},
            {"category": "CRM", "code": "crm:manage", "description": "Create, edit, merge guest profiles and manage guest tags"},

            # Channels & OTAs
            {"category": "Channels", "code": "channels:view", "description": "View connected OTAs, booking channels, and channel allocations"},
            {"category": "Channels", "code": "channels:manage", "description": "Configure channel manager integrations and rate parity sync"},

            # Analytics & Reports
            {"category": "Reports", "code": "reports:view", "description": "View operational dashboards, RevPAR, ADR, and occupancy reports"},
            {"category": "Reports", "code": "reports:export", "description": "Export analytics, financial audits, and guest ledger data"},

            # System & Administration
            {"category": "Settings", "code": "settings:view", "description": "View tenant setup, branding, and system configurations"},
            {"category": "Settings", "code": "settings:manage", "description": "Modify system parameters, taxes, currencies, and shift schedules"},
            {"category": "Settings", "code": "users:view", "description": "View staff users, assigned properties, and active roles"},
            {"category": "Settings", "code": "users:manage", "description": "Invite users, manage staff accounts, and assign custom roles"},
        ]

        permission_objs = {}
        for item in PERMISSIONS_CATALOG:
            perm, created = Permission.objects.update_or_create(
                code=item["code"],
                defaults={
                    "category": item["category"],
                    "description": item["description"]
                }
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
