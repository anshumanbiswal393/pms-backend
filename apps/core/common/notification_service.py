import logging
from django.utils import timezone
from apps.core.common.models import SystemNotification

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def send_notification(
        tenant,
        title: str,
        message: str,
        category: str = "RESERVATION",
        level: str = "info",
        link_url: str = "",
        property_obj = None,
        metadata: dict = None,
        actor_user = None
    ):
        """
        Creates and stores an in-app system notification for the tenant and property.
        """
        try:
            notification = SystemNotification.objects.create(
                tenant=tenant,
                property=property_obj,
                category=category,
                title=title,
                message=message,
                level=level,
                link_url=link_url,
                metadata=metadata or {},
                created_by=actor_user
            )
            logger.info(f"[NOTIFICATION] ({category}) {title} - Created for Tenant {tenant}")
            return notification
        except Exception as e:
            logger.error(f"[NOTIFICATION] Failed to create notification: {e}")
            return None
