import logging
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db import models
from apps.features.channel_manager.models import (
    StaahConfig,
    StaahRoomMapping,
    StaahRateMapping,
)
from apps.features.channel_manager.services.staah_client import StaahSuClient
from apps.features.inventory.models import InventoryUnitType, Amenity
from apps.features.rates.models import RatePlan, RatePlanInventoryType
from apps.booking.models import RoomType as BookingRoomType, RatePlan as BookingRatePlan

logger = logging.getLogger(__name__)

class MappingService:
    """
    Coordinates Room & Rate Plan mapping between PMS models and STAAH Su API.
    """

    def __init__(self, config: StaahConfig):
        self.config = config
        self.client = StaahSuClient(config=config)

    def _resolve_room_rate(
        self,
        mapping: StaahRoomMapping,
        unit_type: Optional[InventoryUnitType] = None,
        booking_room: Optional[BookingRoomType] = None
    ) -> str:
        """
        Dynamically resolves the room rate from StaahRoomMapping, RatePlanInventoryType, or BookingRoomType.
        """
        if mapping.room_rate is not None and mapping.room_rate > 0:
            return f"{float(mapping.room_rate):.2f}"

        if unit_type:
            rate_obj = (
                RatePlanInventoryType.objects.filter(
                    inventory_unit_type=unit_type,
                    is_active=True,
                    base_rate__gt=0,
                    rate_plan__category='bar'
                ).first()
                or RatePlanInventoryType.objects.filter(
                    inventory_unit_type=unit_type,
                    is_active=True,
                    base_rate__gt=0
                ).order_by('base_rate').first()
            )
            if rate_obj and rate_obj.base_rate > 0:
                mapping.room_rate = rate_obj.base_rate
                mapping.save(update_fields=['room_rate'])
                return f"{float(rate_obj.base_rate):.2f}"

        if booking_room and booking_room.base_price and booking_room.base_price > 0:
            mapping.room_rate = booking_room.base_price
            mapping.save(update_fields=['room_rate'])
            return f"{float(booking_room.base_price):.2f}"

        return "0.00"

    def _resolve_room_size(
        self,
        mapping: StaahRoomMapping,
        unit_type: Optional[InventoryUnitType] = None,
        booking_room: Optional[BookingRoomType] = None
    ) -> tuple:
        """
        Resolves size measurement and unit from DB.
        """
        size = mapping.size_measurement
        unit = mapping.size_measurement_unit

        if not size and unit_type and unit_type.size_measurement:
            size = unit_type.size_measurement
        if not size and booking_room and getattr(booking_room, 'size_measurement', None):
            size = booking_room.size_measurement

        if not unit and unit_type and unit_type.size_measurement_unit:
            unit = unit_type.size_measurement_unit
        if not unit and booking_room and getattr(booking_room, 'size_measurement_unit', None):
            unit = booking_room.size_measurement_unit

        size = str(size or '25')
        unit = str(unit or 'sqm')

        if mapping.size_measurement != size or mapping.size_measurement_unit != unit:
            mapping.size_measurement = size
            mapping.size_measurement_unit = unit
            mapping.save(update_fields=['size_measurement', 'size_measurement_unit'])

        return size, unit

    def _resolve_facilities(
        self,
        mapping: StaahRoomMapping,
        unit_type: Optional[InventoryUnitType] = None,
        booking_room: Optional[BookingRoomType] = None
    ) -> List[Dict[str, str]]:
        """
        Resolves room amenities/facilities from DB.
        """
        if mapping.facilities and isinstance(mapping.facilities, list) and len(mapping.facilities) > 0:
            return mapping.facilities

        facilities = []
        if unit_type:
            for type_amenity in unit_type.type_amenities.select_related('amenity').all():
                amenity = type_amenity.amenity
                grp = amenity.category.capitalize() if amenity.category else "Amenities"
                facilities.append({"Group": grp, "name": amenity.name})

        if not facilities and booking_room and getattr(booking_room, 'amenities', None):
            for item in booking_room.amenities:
                if isinstance(item, dict):
                    grp = item.get("Group") or item.get("category") or "Amenities"
                    facilities.append({"Group": grp, "name": item.get("name") or str(item)})
                else:
                    facilities.append({"Group": "Amenities", "name": str(item)})

        if not facilities:
            db_amenities = Amenity.objects.filter(
                models.Q(tenant=self.config.tenant) | models.Q(tenant__isnull=True)
            )[:10]
            for am in db_amenities:
                grp = am.category.capitalize() if am.category else "Amenities"
                facilities.append({"Group": grp, "name": am.name})

        if not facilities:
            facilities = [
                {"Group": "Amenities", "name": "Free WiFi"},
                {"Group": "Amenities", "name": "Air conditioning"},
                {"Group": "Amenities", "name": "Attached Bathroom"},
            ]

        mapping.facilities = facilities
        mapping.save(update_fields=['facilities'])
        return facilities

    def _resolve_description(
        self,
        mapping: StaahRoomMapping,
        unit_type: Optional[InventoryUnitType] = None,
        booking_room: Optional[BookingRoomType] = None
    ) -> str:
        """
        Resolves room description from DB.
        """
        desc = mapping.description
        if not desc and unit_type and unit_type.description:
            desc = unit_type.description
        if not desc and booking_room and booking_room.description:
            desc = booking_room.description
        if not desc:
            desc = f"Comfortable {mapping.pms_room_name} at {self.config.property.name}"

        if mapping.description != desc:
            mapping.description = desc
            mapping.save(update_fields=['description'])
        return desc

    def sync_pms_catalog_to_mappings(self) -> Dict[str, int]:
        """
        Scans PMS RoomTypes and RatePlans and ensures mapping records exist for each.
        """
        rooms_created = 0
        rates_created = 0

        # 1. Scan PMS Core Inventory Unit Types
        pms_unit_types = InventoryUnitType.objects.filter(
            property=self.config.property,
            deleted_at__isnull=True
        )
        for ut in pms_unit_types:
            code = ut.code
            mapping, created = StaahRoomMapping.objects.get_or_create(
                config=self.config,
                pms_room_code=code,
                defaults={
                    'pms_room_name': ut.name,
                    'staah_room_id': f"{self.config.hotel_id}-{code}",
                    'staah_room_name': ut.name,
                    'status': 'Unmapped',
                    'inventory_unit_type': ut,
                    'size_measurement': ut.size_measurement or '25',
                    'size_measurement_unit': ut.size_measurement_unit or 'sqm',
                    'description': ut.description or f"{ut.name} at {self.config.property.name}",
                }
            )
            if not mapping.inventory_unit_type:
                mapping.inventory_unit_type = ut
                mapping.save(update_fields=['inventory_unit_type'])
            if created:
                rooms_created += 1

        # 2. Scan PMS Core Rate Plans
        pms_rate_plans = RatePlan.objects.filter(
            property=self.config.property,
            deleted_at__isnull=True,
            is_active=True
        )
        for rp in pms_rate_plans:
            code = rp.code
            meal_code = rp.default_meal_plan.code if rp.default_meal_plan else 'EP'
            _, created = StaahRateMapping.objects.get_or_create(
                config=self.config,
                pms_rate_code=code,
                defaults={
                    'pms_rate_name': rp.name,
                    'meal_plan_code': meal_code,
                    'staah_rate_id': f"{self.config.hotel_id}-{code}",
                    'staah_rate_name': rp.name,
                    'status': 'Unmapped',
                }
            )
            if created:
                rates_created += 1

        # 3. Fallback: Scan BookingRoomType and BookingRatePlan if no records were found
        if rooms_created == 0 and not StaahRoomMapping.objects.filter(config=self.config).exists():
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
                        'size_measurement': getattr(room, 'size_measurement', '25') or '25',
                        'size_measurement_unit': getattr(room, 'size_measurement_unit', 'sqm') or 'sqm',
                        'room_rate': room.base_price,
                        'description': room.description or f"{room.name} at {self.config.property.name}",
                    }
                )
                if created:
                    rooms_created += 1

        if rates_created == 0 and not StaahRateMapping.objects.filter(config=self.config).exists():
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
        room_list = data.get('roomdetails', [])
        if isinstance(room_list, list):
            for r in room_list:
                room_id = r.get('roomid') or r.get('room_id')
                room_name = r.get('roomname') or r.get('room_name') or room_id

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
        Constructs OTA_HotelRoom payload and pushes a room type to STAAH using dynamic DB values.
        """
        mapping = StaahRoomMapping.objects.get(id=mapping_id, config=self.config)

        # 1. Resolve unit_type from inventory if not already linked
        unit_type = mapping.inventory_unit_type
        if not unit_type:
            unit_type = (
                InventoryUnitType.objects.filter(
                    property=self.config.property,
                    code=mapping.pms_room_code,
                    deleted_at__isnull=True
                ).first()
                or InventoryUnitType.objects.filter(
                    property=self.config.property,
                    name__iexact=mapping.pms_room_name,
                    deleted_at__isnull=True
                ).first()
            )
            if unit_type:
                mapping.inventory_unit_type = unit_type
                mapping.save(update_fields=['inventory_unit_type'])

        # 2. Resolve booking room if applicable
        booking_room = (
            BookingRoomType.objects.filter(
                hotel__name__icontains=self.config.property.name,
                name__iexact=mapping.pms_room_name
            ).first()
            or BookingRoomType.objects.filter(name__iexact=mapping.pms_room_name).first()
        )

        # 3. Resolve all dynamic values
        room_rate_str = self._resolve_room_rate(mapping, unit_type, booking_room)
        size_str, unit_str = self._resolve_room_size(mapping, unit_type, booking_room)
        facilities_list = self._resolve_facilities(mapping, unit_type, booking_room)
        description_str = self._resolve_description(mapping, unit_type, booking_room)

        # Build payload according to Postman collection OTA_HotelRoom schema
        sellable_product = {
            "InvNotifType": "Overlay",
            "InvStatusType": "Modify",
            "roomid": mapping.staah_room_id or mapping.pms_room_code,
            "GuestRoom": {
                "Room": {
                    "RoomRate": room_rate_str,
                    "RoomType": mapping.pms_room_name,
                    "SizeMeasurement": size_str,
                    "SizeMeasurementUnit": unit_str
                },
                "Facilities": {
                    "Facility": facilities_list
                },
                "Description": {
                    "RoomDescription": description_str,
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
