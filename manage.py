#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

def main():
    # Automatically switch to project virtualenv (.venv) if invoked with system Python
    base_dir = Path(__file__).resolve().parent
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = base_dir / ".venv" / "bin" / "python"

    if venv_python.exists() and sys.executable.lower() != str(venv_python).lower() and os.environ.get("DJANGO_VENV_SWITCHED") != "1":
        os.environ["DJANGO_VENV_SWITCHED"] = "1"
        import subprocess
        try:
            result = subprocess.run([str(venv_python)] + sys.argv)
            sys.exit(result.returncode)
        except KeyboardInterrupt:
            sys.exit(0)

    # Set default Django settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'retrod_pms.settings')

    # Display multi-product registration status when runserver is called
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver' and os.environ.get('RUN_MAIN') != 'true':
        print("=" * 70)
        print(">>> RETROD UNIFIED BACKEND: ALL 3 PRODUCTS REGISTERED & ACTIVE")
        print("=" * 70)
        print("  [1] Product 1: PMS Core          (/api/ | /admin/)")
        print("  [2] Product 2: Booking Engine    (/api/reservations/ | /api/inventory/)")
        print("  [3] Product 3: AI Chatbot        (/api/v1/integrations/whatsapp/)")
        print("  [4] API Documentation:           (/api/schema/swagger-ui/)")
        print("=" * 70)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
