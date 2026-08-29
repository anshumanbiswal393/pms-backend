try:
    from .celery import app as celery_app
    app = celery_app
    celery = celery_app
    __all__ = ('celery_app', 'app', 'celery')
except ImportError:
    celery_app = None
    app = None
    celery = None
    __all__ = ()
