import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from django.utils import timezone
from apps.features.channel_manager.models import (
    StaahConfig,
    StaahRoomMapping,
    StaahRateMapping,
)
from apps.features.channel_manager.services.staah_client import StaahSuClient
from apps.features.rates.models import RatePlanInventoryType
from apps.booking.models import (
    RoomType as BookingRoomType,
    RatePlan as BookingRatePlan,
    RoomInventory,
)

logger = logging.getLogger(__name__)

class AriSyncService:
    """
    Availability, Rates, and Inventory (ARI) Push Service.
    Transforms PMS RoomInventory and RatePlans into STAAH Su API format.
    """

    def __init__(self, config: Optional[StaahConfig] = None):
        self.config = config or StaahConfig.objects.filter(is_active=True).first()
        self.client = StaahSuClient(config=self.config) if self.config else None

    def push_inventory_range(
        self,
        date_from: date,
        date_to: date,
        pms_room_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pushes availability, restrictions, and pricing for a date range to STAAH.
        """
        if not self.config or not self.client:
            return {"success": False, "error": "No active STAAH configuration found."}

        # Query room mappings
        room_mappings_qs = StaahRoomMapping.objects.filter(config=self.config, status='Mapped')
        if pms_room_code:
            room_mappings_qs = room_mappings_qs.filter(pms_room_code=pms_room_code)

        if not room_mappings_qs.exists():
            return {
                "success": False, 
                "error": "No mapped room types found. Please map room types in Channel Manager first."
            }

        rate_mappings = list(StaahRateMapping.objects.filter(config=self.config, status='Mapped'))
        primary_rate_id = rate_mappings[0].staah_rate_id if rate_mappings else f"{self.config.hotel_id}-BAR"

        rooms_payload = []
        total_date_entries = 0

        for r_map in room_mappings_qs:
            # Dynamically resolve room rate:
            # 1. StaahRoomMapping.room_rate
            # 2. RatePlanInventoryType base_rate
            # 3. BookingRoomType base_price
            base_price = None
            if r_map.room_rate and r_map.room_rate > 0:
                base_price = float(r_map.room_rate)
            elif r_map.inventory_unit_type:
                rp_it = RatePlanInventoryType.objects.filter(
                    inventory_unit_type=r_map.inventory_unit_type,
                    is_active=True,
                    base_rate__gt=0
                ).first()
                if rp_it and rp_it.base_rate > 0:
                    base_price = float(rp_it.base_rate)

            # Find corresponding PMS RoomType
            pms_room = BookingRoomType.objects.filter(
                models_code=r_map.pms_room_code
            ).first() if hasattr(BookingRoomType, 'models_code') else BookingRoomType.objects.filter(
                name__iexact=r_map.pms_room_name
            ).first()

            if not pms_room:
                pms_room = BookingRoomType.objects.filter(is_active=True).first()

            if base_price is None:
                base_price = float(pms_room.base_price) if pms_room else 2500.0
            total_rooms = pms_room.total_rooms if pms_room else 10

            # Fetch extra adult and child rates dynamically from RatePlan if available
            pms_rate_plan = BookingRatePlan.objects.filter(room_type=pms_room).first() if pms_room else None
            extra_adult = float(pms_rate_plan.extra_adult_price) if (pms_rate_plan and pms_rate_plan.extra_adult_price) else 0.0
            extra_child = float(pms_rate_plan.extra_child_price) if (pms_rate_plan and pms_rate_plan.extra_child_price) else 0.0

            # Gather date by date inventory
            curr_date = date_from
            date_entries = []

            while curr_date <= date_to:
                date_str = curr_date.strftime("%Y-%m-%d")

                # Check if specific RoomInventory record exists
                inv = None
                if pms_room:
                    inv = RoomInventory.objects.filter(room_type=pms_room, date=curr_date).first()

                available_rooms = inv.available_rooms if inv else total_rooms
                custom_price = float(inv.custom_price) if (inv and inv.custom_price) else base_price
                is_blocked = inv.is_blocked if inv else False
                min_los = inv.min_los if inv else 1
                max_los = inv.max_los if inv else 30
                cta = inv.closed_to_arrival if inv else False
                ctd = inv.closed_to_departure if inv else False

                date_entries.append({
                    "from": date_str,
                    "to": date_str,
                    "rate": [
                        {"rateplanid": primary_rate_id}
                    ],
                    "roomstosell": str(max(0, available_rooms)),
                    "price": [
                        {"NumberOfGuests": "1", "value": f"{custom_price:.2f}"},
                        {"NumberOfGuests": "2", "value": f"{custom_price:.2f}"}
                    ],
                    "closed": "1" if is_blocked else "0",
                    "minimumstay": str(min_los),
                    "maximumstay": str(max_los),
                    "closedonarrival": "1" if cta else "0",
                    "closedondeparture": "1" if ctd else "0",
                    "extraadultrate": f"{extra_adult:.2f}",
                    "extrachildrate": f"{extra_child:.2f}"
                })

                total_date_entries += 1
                curr_date += timedelta(days=1)

            rooms_payload.append({
                "roomid": r_map.staah_room_id,
                "date": date_entries
            })

        # Push to STAAH
        res = self.client.push_availability(rooms_payload)
        res["records_synced"] = total_date_entries
        return res

    def push_room_availability_for_dates(
        self,
        room_name: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Called when a reservation is created or modified to immediately update STAAH.
        """
        if not self.config or not self.config.auto_sync_inventory:
            return {"skipped": True, "reason": "auto_sync_inventory disabled"}

        # Find matching room mapping
        r_map = StaahRoomMapping.objects.filter(
            config=self.config,
            pms_room_name__iexact=room_name
        ).first()

        pms_code = r_map.pms_room_code if r_map else None
        return self.push_inventory_range(start_date, end_date, pms_room_code=pms_code)
