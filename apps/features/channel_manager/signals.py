import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.booking.models import Booking, RoomInventory
from apps.features.channel_manager.services.ari_sync import AriSyncService


logger = logging.getLogger(__name__)

@receiver(post_save, sender=Booking)
def on_booking_saved(sender, instance, created, **kwargs):
    """
    Realtime trigger: When a booking is created or updated, immediately update
    available rooms on STAAH Su API for the affected date range.
    """
    try:
        service = AriSyncService()
        if not service.config or not service.config.auto_sync_inventory:
            return

        room_name = instance.room_type.name if instance.room_type else ""
        if room_name and instance.check_in and instance.check_out:
            logger.info(f"Triggering realtime ARI sync for {room_name} ({instance.check_in} to {instance.check_out})")
            service.push_room_availability_for_dates(
                room_name=room_name,
                start_date=instance.check_in,
                end_date=instance.check_out
            )
    except Exception as e:
        logger.error(f"Failed to auto-sync ARI on booking save: {str(e)}")


@receiver(post_delete, sender=Booking)
def on_booking_deleted(sender, instance, **kwargs):
    """
    Realtime trigger: When a booking is deleted/cancelled, release inventory on STAAH.
    """
    try:
        service = AriSyncService()
        if not service.config or not service.config.auto_sync_inventory:
            return

        room_name = instance.room_type.name if instance.room_type else ""
        if room_name and instance.check_in and instance.check_out:
            logger.info(f"Triggering realtime ARI release for {room_name} ({instance.check_in} to {instance.check_out})")
            service.push_room_availability_for_dates(
                room_name=room_name,
                start_date=instance.check_in,
                end_date=instance.check_out
            )
    except Exception as e:
        logger.error(f"Failed to auto-sync ARI on booking delete: {str(e)}")


@receiver(post_save, sender=RoomInventory)
def on_room_inventory_saved(sender, instance, **kwargs):
    """
    Realtime trigger: When front desk updates room inventory/rates or toggles stop-sell.
    """
    try:
        service = AriSyncService()
        if not service.config or not service.config.auto_sync_inventory:
            return

        room_name = instance.room_type.name if instance.room_type else ""
        if room_name and instance.date:
            service.push_room_availability_for_dates(
                room_name=room_name,
                start_date=instance.date,
                end_date=instance.date
            )
    except Exception as e:
        logger.error(f"Failed to auto-sync ARI on RoomInventory save: {str(e)}")
