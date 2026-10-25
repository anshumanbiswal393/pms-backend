"""
Verify PMS PostgreSQL connectivity before POS smokes/migrations.

  python manage.py check_pos_db
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.conf import settings


class Command(BaseCommand):
    help = "Ping shared PMS PostgreSQL and list POS tables."

    def handle(self, *args, **options):
        db = settings.DATABASES["default"]
        engine = db.get("ENGINE", "")
        if "postgresql" not in engine:
            raise CommandError(f"Expected PostgreSQL, got {engine}")

        self.stdout.write(f"ENGINE={engine}")
        self.stdout.write(f"HOST={db.get('HOST')}")
        self.stdout.write(f"NAME={db.get('NAME')}")

        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                ping = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public' AND tablename LIKE 'pos_%%'
                    ORDER BY 1
                    """
                )
                tables = [row[0] for row in cursor.fetchall()]
        except Exception as exc:
            raise CommandError(f"CONNECTION_FAIL: {exc}") from exc

        self.stdout.write(f"PING={ping}")
        self.stdout.write(f"POS_TABLES={len(tables)}")
        for name in tables:
            self.stdout.write(f" - {name}")
        self.stdout.write(self.style.SUCCESS("CONNECTION_OK"))
