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

            {"category": "Reservations", "code": "reservations.view", "description": "View reservation calendar, timeline, and booking details"},
            {"category": "Reservations", "code": "reservations.create", "description": "Create new reservations and group blocks"},
            {"category": "Reservations", "code": "reservations.edit", "description": "Edit guest details, room assignments, and stay dates"},
            {"category": "Reservations", "code": "reservations.cancel", "description": "Cancel active bookings and process cancellation policies"},
            {"category": "Reservations", "code": "reservations.manage", "description": "Full reservation control and policy override"},

            # Rooms & Inventory
            {"category": "Inventory", "code": "inventory:view", "description": "View room status, unit types, and floor plans"},
            {"category": "Inventory", "code": "inventory:manage", "description": "Create and edit unit types, room amenities, and room attributes"},
            {"category": "Inventory", "code": "inventory:layout", "description": "Configure building layouts, floor maps, and unit matrices"},
            {"category": "Inventory", "code": "inventory:status", "description": "Update out-of-order and out-of-service room statuses"},

            {"category": "Inventory", "code": "inventory.view", "description": "View room status, unit types, and floor plans"},
            {"category": "Inventory", "code": "inventory.create", "description": "Create unit types, rooms, amenities, and room attributes"},
            {"category": "Inventory", "code": "inventory.edit", "description": "Edit unit types, rooms, amenities, and room attributes"},
            {"category": "Inventory", "code": "inventory.delete", "description": "Delete unit types, rooms, amenities, and room attributes"},
            {"category": "Inventory", "code": "inventory.manage", "description": "Full management of unit types, rooms, amenities, and room attributes"},

            {"category": "Rooms", "code": "rooms.view", "description": "View room types and room details"},
            {"category": "Rooms", "code": "rooms.create", "description": "Create room types and room numbers"},
            {"category": "Rooms", "code": "rooms.edit", "description": "Edit room types and room numbers"},
            {"category": "Rooms", "code": "rooms.delete", "description": "Delete room types and room numbers"},
            {"category": "Rooms", "code": "rooms.manage", "description": "Full management of room types and room inventory"},

            # Rates & Pricing Strategies
            {"category": "Rates", "code": "rates:view", "description": "View rate plans, seasonal pricing, and occupancy multipliers"},
            {"category": "Rates", "code": "rates:manage", "description": "Configure rate plans, rate rules, and dynamic pricing rules"},
            {"category": "Rates", "code": "rates:packages", "description": "Configure hospitality packages and meal plan pricing"},

            {"category": "Rates", "code": "rates.view", "description": "View rate plans, seasonal pricing, and occupancy multipliers"},
            {"category": "Rates", "code": "rates.create", "description": "Create rate plans and rate rules"},
            {"category": "Rates", "code": "rates.edit", "description": "Edit rate plans and rate rules"},
            {"category": "Rates", "code": "rates.delete", "description": "Delete rate plans and rate rules"},
            {"category": "Rates", "code": "rates.manage", "description": "Full rate management and pricing rules override"},

            # Services & Add-Ons Catalog
            {"category": "Services", "code": "services:view", "description": "View extra service offerings and amenity catalog"},
            {"category": "Services", "code": "services:manage", "description": "Create and edit additional guest services and service categories"},

            # Billing & Invoicing
            {"category": "Billing", "code": "billing:view", "description": "View guest folios, invoices, and payment receipts"},
            {"category": "Billing", "code": "billing:post", "description": "Post custom charges, room charges, and minibar fees"},
            {"category": "Billing", "code": "billing:settle", "description": "Settle guest folios and accept payments"},
            {"category": "Billing", "code": "billing:refund", "description": "Process payment refunds and billing adjustments"},

            {"category": "Billing", "code": "billing.view", "description": "View guest folios, invoices, and payment receipts"},
            {"category": "Billing", "code": "billing.manage", "description": "Full billing management, settlements, refunds, and adjustments"},

            # Housekeeping & Maintenance
            {"category": "Housekeeping", "code": "housekeeping:view", "description": "View housekeeping tasks, linen assignments, and room cleaning statuses"},
            {"category": "Housekeeping", "code": "housekeeping:assign", "description": "Assign housekeepers to rooms and deep cleaning schedules"},
            {"category": "Housekeeping", "code": "housekeeping:status", "description": "Update room cleaning and inspection status"},
            {"category": "Housekeeping", "code": "maintenance:view", "description": "View maintenance tickets and asset issues"},
            {"category": "Housekeeping", "code": "maintenance:manage", "description": "Create and manage maintenance tickets and asset repairs"},

            {"category": "Housekeeping", "code": "housekeeping.view", "description": "View housekeeping tasks and room cleaning status"},
            {"category": "Housekeeping", "code": "housekeeping.manage", "description": "Manage housekeeping assignments and schedules"},
            {"category": "Maintenance", "code": "maintenance.view", "description": "View maintenance tickets and repairs"},
            {"category": "Maintenance", "code": "maintenance.manage", "description": "Manage maintenance tickets and repairs"},

            # CRM & Guests
            {"category": "CRM", "code": "crm:view", "description": "View guest profiles, stay history, and contact details"},
            {"category": "CRM", "code": "crm:manage", "description": "Create, edit, merge guest profiles and manage guest tags"},

            {"category": "Guests", "code": "guests.view", "description": "View guest profiles"},
            {"category": "Guests", "code": "guests.create", "description": "Create guest profiles"},
            {"category": "Guests", "code": "guests.edit", "description": "Edit guest profiles"},
            {"category": "Guests", "code": "guests.manage", "description": "Full guest profile management"},

            # Channels & OTAs
            {"category": "Channels", "code": "channels:view", "description": "View connected OTAs, booking channels, and channel allocations"},
            {"category": "Channels", "code": "channels:manage", "description": "Configure channel manager integrations and rate parity sync"},

            # Analytics & Reports
            {"category": "Reports", "code": "reports:view", "description": "View operational dashboards, RevPAR, ADR, and occupancy reports"},
            {"category": "Reports", "code": "reports:export", "description": "Export analytics, financial audits, and guest ledger data"},

            {"category": "Reports", "code": "reports.view", "description": "View operational dashboards and analytics"},
            {"category": "Reports", "code": "reports.manage", "description": "Full management of operational reports"},

            # System & Administration
            {"category": "Settings", "code": "settings:view", "description": "View tenant setup, branding, and system configurations"},
            {"category": "Settings", "code": "settings:manage", "description": "Modify system parameters, taxes, currencies, and shift schedules"},
            {"category": "Settings", "code": "users:view", "description": "View staff users, assigned properties, and active roles"},
            {"category": "Settings", "code": "users:manage", "description": "Invite users, manage staff accounts, and assign custom roles"},

            {"category": "Settings", "code": "settings.view", "description": "View system settings"},
            {"category": "Settings", "code": "settings.manage", "description": "Manage system settings and configurations"},
            {"category": "Staff", "code": "staff.view", "description": "View staff profiles"},
            {"category": "Staff", "code": "staff.manage", "description": "Manage staff accounts and permissions"},
            {"category": "Roles", "code": "roles.view", "description": "View roles and permissions"},
            {"category": "Roles", "code": "roles.manage", "description": "Manage roles and permission assignments"},
            {"category": "Dashboard", "code": "dashboard.view", "description": "View main dashboard"},
            {"category": "Audit", "code": "audit.view", "description": "View audit logs"}
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

        all_permission_codes = list(permission_objs.keys())

        # Global Roles Definition
        ROLES_CATALOG = [
            {
                "code": "super_admin",
                "name": "Super Admin",
                "description": "Full master developer control over all platform modules and tenants.",
                "permissions": all_permission_codes
            },
            {
                "code": "owner",
                "name": "Owner",
                "description": "Full property group management and operational control.",
                "permissions": all_permission_codes
            },
            {
                "code": "general_manager",
                "name": "General Manager",
                "description": "Full property local operations management.",
                "permissions": all_permission_codes
            },
            {
                "code": "front_office_manager",
                "name": "Front Office Manager",
                "description": "Front desk oversight, check-ins, check-outs, and guest folios.",
                "permissions": [
                    "reservations:view", "reservations:create", "reservations:update", "reservations:cancel", "reservations:checkin", "reservations:checkout",
                    "reservations.view", "reservations.create", "reservations.edit", "reservations.cancel", "reservations.manage",
                    "inventory:view", "inventory:status", "inventory.view", "rooms.view",
                    "rates:view", "rates.view", "services:view",
                    "billing:view", "billing:post", "billing:settle", "billing:refund", "billing.view",
                    "crm:view", "crm:manage", "guests.view", "guests.edit",
                    "reports:view", "reports.view"
                ]
            },
            {
                "code": "front_desk_agent",
                "name": "Front Desk Agent",
                "description": "Front office check-in/check-out transactions and folio billing.",
                "permissions": [
                    "reservations:view", "reservations:create", "reservations:update", "reservations:checkin", "reservations:checkout",
                    "reservations.view", "reservations.create", "reservations.edit",
                    "inventory:view", "inventory.view", "rooms.view",
                    "billing:view", "billing:post", "billing:settle", "billing.view",
                    "crm:view", "crm:manage", "guests.view"
                ]
            },
            {
                "code": "housekeeping_supervisor",
                "name": "Housekeeping Supervisor",
                "description": "Room status coordination and maintenance task assignment.",
                "permissions": [
                    "inventory:view", "inventory:status", "inventory.view", "rooms.view",
                    "housekeeping:view", "housekeeping:assign", "housekeeping:status", "housekeeping.view", "housekeeping.manage",
                    "maintenance:view", "maintenance:manage", "maintenance.view", "maintenance.manage"
                ]
            },
            {
                "code": "accounts",
                "name": "Accounts",
                "description": "Invoices and balance settlement processing.",
                "permissions": [
                    "billing:view", "billing:post", "billing:settle", "billing:refund", "billing.view", "billing.manage",
                    "rates:view", "rates.view", "services:view",
                    "reports:view", "reports:export", "reports.view"
                ]
            }
        ]

        role_count = 0
        role_perm_count = 0

        for r_data in ROLES_CATALOG:
            # Seed both global (tenant=None) and existing tenant roles
            matching_roles = list(Role.objects.filter(code=r_data["code"]))
            if not any(r.tenant is None for r in matching_roles):
                global_role, _ = Role.objects.update_or_create(
                    tenant=None,
                    code=r_data["code"],
                    defaults={
                        "name": r_data["name"],
                        "description": r_data["description"]
                    }
                )
                matching_roles.append(global_role)

            for role in matching_roles:
                role_count += 1
                for p_code in r_data["permissions"]:
                    if p_code in permission_objs:
                        _, created = RolePermission.objects.get_or_create(
                            role=role,
                            permission=permission_objs[p_code]
                        )
                        if created:
                            role_perm_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {role_count} roles with {role_perm_count} role-permission mappings!"
        ))

