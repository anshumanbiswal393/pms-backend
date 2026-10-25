"""
Deprecated: POS/PMS tests must use the shared PostgreSQL DATABASE_URL from settings.

This module now re-exports production settings so accidental imports do not
force SQLite. Prefer:

  python manage.py test apps.POS.tests... --keepdb --noinput
"""
from retrod_pms.settings import *  # noqa: F401,F403
