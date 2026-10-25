"""
Connection-gated smoke suite for POS Parts 1–5.

  python manage.py smoke_all_parts
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Ping PostgreSQL then run Parts 2–5 smoke commands sequentially."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== POS DB connection ==="))
        call_command("check_pos_db")

        steps = [
            ("Part 2 menu", "smoke_pos_menu"),
            ("Part 3 orders", "smoke_pos_orders"),
            ("Part 4 folio", "smoke_pos_folio"),
            ("Part 5 dues", "smoke_pos_dues"),
            ("Part 6 stock", "smoke_pos_stock"),
        ]
        failed = []
        for label, cmd in steps:
            self.stdout.write(self.style.MIGRATE_HEADING(f"=== {label} ==="))
            try:
                # Re-check connection before each part
                call_command("check_pos_db")
                call_command(cmd)
                self.stdout.write(self.style.SUCCESS(f"OK {label}"))
            except Exception as exc:
                failed.append((label, str(exc)))
                self.stdout.write(self.style.ERROR(f"FAIL {label}: {exc}"))

        if failed:
            detail = "; ".join(f"{n}: {e}" for n, e in failed)
            raise CommandError(f"Smoke suite incomplete — {detail}")

        self.stdout.write(
            self.style.SUCCESS("All Parts 2–6 smokes passed with CONNECTION_OK")
        )
