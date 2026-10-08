from django.apps import AppConfig

class ChannelManagerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.features.channel_manager'
    verbose_name = 'Channel Manager (STAAH Su API)'

    def ready(self):
        try:
            import apps.features.channel_manager.signals
        except Exception:
            pass
