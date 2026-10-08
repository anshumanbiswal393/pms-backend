import logging
from typing import Dict, Any, List, Optional
from django.utils import timezone
from apps.features.channel_manager.models import (
    StaahConfig,
    StaahRoomMapping,
    StaahRateMapping,
)
from apps.features.channel_manager.services.staah_client import StaahSuClient
from apps.booking.models import RoomType as BookingRoomType, RatePlan as BookingRatePlan

logger = logging.getLogger(__name__)

class MappingService:
    """
    Coordinates Room & Rate Plan mapping between PMS models and STAAH Su API.
    """

    def __init__(self, config: StaahConfig):
        self.config = config
        self.client = StaahSuClient(config=config)

    def sync_pms_catalog_to_mappings(self) -> Dict[str, int]:
        """
        Scans PMS RoomTypes and RatePlans and ensures mapping records exist for each.
        """
        rooms_created = 0
        rates_created = 0

        # Scan PMS Room Types
        pms_rooms = BookingRoomType.objects.filter(is_active=True)
        for room in pms_rooms:
            code = room.slug or f"ROOM-{room.id}"
            _, created = StaahRoomMapping.objects.get_or_create(
                config=self.config,
                pms_room_code=code,
                defaults={
                    'pms_room_name': room.name,
                    'staah_room_id': f"{self.config.hotel_id}-{code}",
                    'staah_room_name': room.name,
                    'status': 'Unmapped',
                }
            )
            if created:
                rooms_created += 1

        # Scan PMS Rate Plans
        pms_rates = BookingRatePlan.objects.all()
        for rate in pms_rates:
            code = f"RATE-{rate.id}"
            _, created = StaahRateMapping.objects.get_or_create(
                config=self.config,
                pms_rate_code=code,
                defaults={
                    'pms_rate_name': rate.title,
                    'meal_plan_code': 'EP',
                    'staah_rate_id': f"{self.config.hotel_id}-{code}",
                    'staah_rate_name': rate.title,
                    'status': 'Unmapped',
                }
            )
            if created:
                rates_created += 1

        return {"rooms_synced": rooms_created, "rates_synced": rates_created}

    def fetch_and_merge_staah_rooms(self) -> Dict[str, Any]:
        """
        Calls STAAH POST /SUAPI/jservice/roomdetails and merges active remote rooms.
        """
        res = self.client.fetch_room_details()
        if not res.get('success'):
            return res

        data = res.get('data', {})
        # STAAH response structure: { "roomdetails": [ { "roomid": "...", "roomname": "..." }, ... ] }
        room_list = data.get('roomdetails', [])
        if isinstance(room_list, list):
            for r in room_list:
                room_id = r.get('roomid') or r.get('room_id')
                room_name = r.get('roomname') or r.get('room_name') or room_id

                # Match by room name or similar code
                mapping = StaahRoomMapping.objects.filter(
                    config=self.config,
                    staah_room_id=room_id
                ).first()

                if not mapping:
                    mapping = StaahRoomMapping.objects.filter(
                        config=self.config,
                        pms_room_name__iexact=room_name
                    ).first()

                if mapping:
                    mapping.staah_room_id = room_id
                    mapping.staah_room_name = room_name
                    mapping.status = 'Mapped'
                    mapping.last_synced_at = timezone.now()
                    mapping.save(update_fields=['staah_room_id', 'staah_room_name', 'status', 'last_synced_at'])

        return {
            "success": True,
            "remote_rooms": room_list,
            "message": f"Successfully retrieved {len(room_list)} room types from STAAH."
        }

    def fetch_and_merge_staah_rates(self) -> Dict[str, Any]:
        """
        Calls STAAH POST /SUAPI/jservice/ratedetails and merges active remote rate plans.
        """
        res = self.client.fetch_rate_details()
        if not res.get('success'):
            return res

        data = res.get('data', {})
        rate_list = data.get('ratedetails', [])
        if isinstance(rate_list, list):
            for r in rate_list:
                rate_id = r.get('rateplanid') or r.get('rate_id')
                rate_name = r.get('rateplanname') or r.get('rate_name') or rate_id
                meal_plan = str(r.get('MealPlanID', '1'))

                mapping = StaahRateMapping.objects.filter(
                    config=self.config,
                    staah_rate_id=rate_id
                ).first()

                if not mapping:
                    mapping = StaahRateMapping.objects.filter(
                        config=self.config,
                        pms_rate_name__iexact=rate_name
                    ).first()

                if mapping:
                    mapping.staah_rate_id = rate_id
                    mapping.staah_rate_name = rate_name
                    mapping.meal_plan_code = meal_plan
                    mapping.status = 'Mapped'
                    mapping.last_synced_at = timezone.now()
                    mapping.save(update_fields=['staah_rate_id', 'staah_rate_name', 'meal_plan_code', 'status', 'last_synced_at'])

        return {
            "success": True,
            "remote_rates": rate_list,
            "message": f"Successfully retrieved {len(rate_list)} rate plans from STAAH."
        }

    def push_room_to_staah(self, mapping_id: str) -> Dict[str, Any]:
        """
        Constructs OTA_HotelRoom payload and pushes a room type to STAAH.
        """
        mapping = StaahRoomMapping.objects.get(id=mapping_id, config=self.config)
        
        # Build payload according to Postman collection OTA_HotelRoom schema
        sellable_product = {
            "InvNotifType": "Overlay",
            "InvStatusType": "Modify",
            "roomid": mapping.staah_room_id or mapping.pms_room_code,
            "GuestRoom": {
                "Room": {
                    "RoomRate": "2000.00",
                    "RoomType": mapping.pms_room_name,
                    "SizeMeasurement": "25",
                    "SizeMeasurementUnit": "sqm"
                },
                "Facilities": {
                    "Facility": [
                        {"Group": "Amenities", "name": "Free WiFi"},
                        {"Group": "Amenities", "name": "Air conditioning"},
                        {"Group": "Amenities", "name": "Attached Bathroom"},
                    ]
                },
                "Description": {
                    "RoomDescription": f"Comfortable {mapping.pms_room_name} at {self.config.property.name}",
                    "Text": mapping.pms_room_name
                }
            }
        }

        res = self.client.sync_room_type(sellable_product)
        if res.get('success'):
            mapping.status = 'Mapped'
            mapping.last_synced_at = timezone.now()
            mapping.save(update_fields=['status', 'last_synced_at'])

        return res

    def push_rate_to_staah(self, mapping_id: str) -> Dict[str, Any]:
        """
        Constructs OTA_HotelRatePlan payload and pushes a rate plan to STAAH.
        """
        mapping = StaahRateMapping.objects.get(id=mapping_id, config=self.config)

        rate_plan_payload = {
            "RatePlanNotifType": "New",
            "rateplanid": mapping.staah_rate_id or mapping.pms_rate_code,
            "MealPlanID": mapping.meal_plan_code or "1",
            "closeoutdays": "0",
            "closeouttime": "00:30",
            "Description": {
                "Name": mapping.staah_rate_name or mapping.pms_rate_name,
                "Text": f"Rate plan {mapping.pms_rate_name}"
            }
        }

        res = self.client.sync_rate_plan(rate_plan_payload)
        if res.get('success'):
            mapping.status = 'Mapped'
            mapping.last_synced_at = timezone.now()
            mapping.save(update_fields=['status', 'last_synced_at'])

        return res
