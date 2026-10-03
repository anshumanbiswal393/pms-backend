import re
from decimal import Decimal
from django.db import models


def parse_time_string(raw: str) -> str:
    if not raw:
        return ""
    raw = str(raw).strip()
    if ':' not in raw and '.' in raw:
        try:
            h = int(float(raw))
            am_pm = 'AM' if h < 12 else 'PM'
            h12 = h % 12 or 12
            return f"{h12:02d}:00 {am_pm}"
        except Exception:
            pass
    return raw


def sync_pms_property_to_booking_engine(prop_or_dict):
    """
    Synchronizes PMS Property data into apps.booking models (Hotel, RoomType, RatePlan, HotelImage,
    HotelAmenity, Policy, PromoCode, AddonPackage, PaymentGateway).
    Accepts either a Property model instance or a dictionary.
    """
    from apps.booking.models import (
        Hotel, HotelImage, RoomType, RatePlan, Amenity, HotelAmenity,
        Policy, PromoCode, AddonPackage, PaymentGateway
    )

    if hasattr(prop_or_dict, 'booking_engine_settings'):
        # Model instance
        pms_p = {
            'id': str(prop_or_dict.id),
            'hotel_id': getattr(prop_or_dict, 'hotel_id', ''),
            'name': prop_or_dict.name,
            'description': prop_or_dict.description or '',
            'address_line_1': prop_or_dict.address_line_1 or '',
            'city': prop_or_dict.city or '',
            'state': prop_or_dict.state or '',
            'postal_code': prop_or_dict.postal_code or '',
            'contact_phone': prop_or_dict.contact_phone or '',
            'contact_email': prop_or_dict.contact_email or '',
            'check_in_time': prop_or_dict.check_in_time or '',
            'check_out_time': prop_or_dict.check_out_time or '',
            'google_map_url': prop_or_dict.google_map_url or '',
            'website_logo': prop_or_dict.website_logo or '',
            'image_url': prop_or_dict.image_url or '',
            'photos': prop_or_dict.photos or [],
            'amenities': prop_or_dict.amenities or [],
            'house_rules': prop_or_dict.house_rules or '',
            'cancellation_policy': prop_or_dict.cancellation_policy or '',
            'refund_policy': prop_or_dict.refund_policy or '',
            'booking_engine_settings': prop_or_dict.booking_engine_settings or {},
        }
    else:
        pms_p = dict(prop_or_dict or {})

    settings = pms_p.get('booking_engine_settings') or {}
    
    # ── Canonical Slug Resolution ───────────────────────────────────────────────
    raw_slug = settings.get('slug') or pms_p.get('slug') or pms_p.get('name', 'hotel')
    canonical_slug = re.sub(r'[^a-z0-9]+', '-', str(raw_slug).lower()).strip('-')
    if not canonical_slug:
        canonical_slug = f"hotel-{pms_p.get('id', 'retrod')}"

    # ── Find or Create Hotel Model ──────────────────────────────────────────────
    hotel = Hotel.objects.filter(slug__iexact=canonical_slug).first()
    if not hotel:
        # Also check if any hotel exists with clean matching slug
        for h in Hotel.objects.all():
            if re.sub(r'[^a-z0-9]', '', h.slug) == re.sub(r'[^a-z0-9]', '', canonical_slug):
                hotel = h
                break

    if not hotel:
        hotel = Hotel(slug=canonical_slug)

    # Ensure slug is updated to canonical
    hotel.slug = canonical_slug

    # ── Core Profile Synchronization ───────────────────────────────────────────
    hero_slides = settings.get('hero_slides') or []
    if not hero_slides and canonical_slug in ['retrod', 'demo-retrod', 'demo']:
        hero_slides = [
            '/hotel-slides/hotel-slide-1.png',
            '/hotel-slides/hotel-slide-2.png',
            '/hotel-slides/hotel-slide-3.png',
            '/hotel-slides/hotel-slide-4.png'
        ]
    hero_url = hero_slides[0] if hero_slides else (pms_p.get('image_url') or "")

    hotel.name = settings.get('name') or pms_p.get('name') or canonical_slug.replace('-', ' ').title()
    hotel.tagline = settings.get('tagline') or ''
    
    about_desc = settings.get('about_description') or pms_p.get('description') or ''
    hotel.description = about_desc
    hotel.short_description = (
        settings.get('google_editorial_summary') or
        pms_p.get('short_description') or
        settings.get('about_description') or
        pms_p.get('description') or
        ''
    )

    hotel.address = pms_p.get('address_line_1') or settings.get('address') or ''
    hotel.city = pms_p.get('city') or settings.get('city') or ''
    hotel.state = pms_p.get('state') or settings.get('state') or ''
    hotel.pincode = pms_p.get('postal_code') or settings.get('pincode') or ''
    hotel.phone = pms_p.get('contact_phone') or settings.get('phone') or ''
    hotel.email = pms_p.get('contact_email') or settings.get('email') or ''
    hotel.whatsapp = settings.get('whatsapp') or pms_p.get('contact_phone') or settings.get('phone') or ''

    pms_checkin = parse_time_string(pms_p.get('check_in_time') or settings.get('check_in_time'))
    pms_checkout = parse_time_string(pms_p.get('check_out_time') or settings.get('check_out_time'))
    hotel.check_in_time = pms_checkin or '12:00 PM'
    hotel.check_out_time = pms_checkout or '11:00 AM'

    hotel.map_embed_url = settings.get('google_map_url') or pms_p.get('google_map_url') or ''
    hotel.logo_url = settings.get('logo_url') or settings.get('website_logo') or pms_p.get('website_logo') or pms_p.get('logo_url') or ''
    hotel.hero_banner_url = hero_url or ''

    # Social links
    hotel.facebook_url = settings.get('facebook_url') or settings.get('facebook') or ''
    hotel.instagram_url = settings.get('instagram_url') or settings.get('instagram') or ''
    hotel.twitter_url = settings.get('twitter_url') or settings.get('twitter') or ''
    hotel.linkedin_url = settings.get('linkedin_url') or settings.get('linkedin') or ''
    hotel.youtube_url = settings.get('youtube_url') or settings.get('youtube') or ''

    # Theming & Storytelling
    hotel.page_title = settings.get('page_title') or f"Welcome to {hotel.name}"
    hotel.theme_color = settings.get('theme_color') or "#ffc107"
    hotel.what_makes_special = settings.get('what_makes_special') or ''
    hotel.backstory = settings.get('backstory') or ''

    # Google Reviews & Ratings
    google_reviews = (
        settings.get('google_reviews') or
        settings.get('google_reviews_data') or
        pms_p.get('reviews_data') or
        pms_p.get('google_reviews_data') or
        []
    )
    hotel.google_reviews_data = google_reviews if isinstance(google_reviews, list) else []

    if settings.get('enable_google_reviews') is not None:
        hotel.enable_google_reviews = bool(settings.get('enable_google_reviews'))
    elif pms_p.get('enable_google_reviews') is not None:
        hotel.enable_google_reviews = bool(pms_p.get('enable_google_reviews'))
    else:
        hotel.enable_google_reviews = True

    g_rating = settings.get('google_rating') or pms_p.get('google_rating')
    if g_rating is not None and str(g_rating).strip() != "" and str(g_rating).strip() != "0":
        try:
            hotel.google_rating = Decimal(str(g_rating))
        except Exception:
            hotel.google_rating = Decimal('4.8')
    else:
        hotel.google_rating = Decimal('4.8')

    g_count = settings.get('google_review_count') or pms_p.get('total_reviews')
    if g_count is not None and str(g_count).strip() != "" and str(g_count).strip() != "0":
        try:
            hotel.total_reviews = int(g_count)
        except Exception:
            hotel.total_reviews = 148
    else:
        hotel.total_reviews = 148

    from django.db import transaction
    from django.core.cache import cache

    with transaction.atomic():
        hotel.booking_engine_settings = settings
        hotel.save()

        # ── Image Gallery Synchronization ──────────────────────────────────────────
        HotelImage.objects.filter(hotel=hotel).delete()
        seen_image_urls = set()
        images_to_create = []

        for idx, url in enumerate(hero_slides, start=1):
            if url and isinstance(url, str) and url.strip():
                u = url.strip()
                if u not in seen_image_urls:
                    images_to_create.append(
                        HotelImage(
                            hotel=hotel, image_url=u, category='hero',
                            caption=f'{hotel.name} Banner {idx}', sort_order=idx
                        )
                    )
                    seen_image_urls.add(u)

        gallery_images = settings.get('images') or pms_p.get('photos') or []
        for idx, img in enumerate(gallery_images, start=1):
            if isinstance(img, dict):
                img_url = img.get('image_url') or img.get('imageUrl') or img.get('url') or ''
                cap = img.get('caption', f'{hotel.name} Gallery {idx}')
                order = img.get('displayOrder') or img.get('sort_order') or idx
            else:
                img_url = str(img)
                cap = f'{hotel.name} Gallery {idx}'
                order = idx

            if img_url and img_url.strip():
                u = img_url.strip()
                if u not in seen_image_urls:
                    images_to_create.append(
                        HotelImage(
                            hotel=hotel, image_url=u, category='gallery',
                            caption=cap, sort_order=order
                        )
                    )
                    seen_image_urls.add(u)

        if images_to_create:
            HotelImage.objects.bulk_create(images_to_create)

        # ── Room Types & Rate Plans Synchronization ────────────────────────────────
        custom_rooms = (
            settings.get('custom_room_types') or
            settings.get('room_types') or
            pms_p.get('room_types') or
            []
        )
        rates_matrix = settings.get('rates_matrix') or {}

        # If no custom_room_types configured yet, check if property has PMS InventoryUnitTypes
        if not custom_rooms:
            try:
                from apps.features.inventory.models import InventoryUnitType
                from apps.core.tenants.models import Property as PmsProperty
                prop_id = pms_p.get('id')
                p_obj = None
                if prop_id:
                    try:
                        p_obj = PmsProperty.objects.filter(id=prop_id).first()
                    except Exception:
                        pass
                if not p_obj:
                    p_obj = PmsProperty.objects.filter(name__iexact=hotel.name).first()
                if p_obj:
                    pms_units = InventoryUnitType.objects.filter(property=p_obj, deleted_at__isnull=True)
                    if pms_units.exists():
                        custom_rooms = []
                        for idx, u in enumerate(pms_units, start=1):
                            u_slug = re.sub(r'[^a-z0-9]+', '-', u.name.lower()).strip('-') or f"room-{idx}"
                            u_base = float(getattr(u, 'base_price', 0) or 0)
                            custom_rooms.append({
                                'id': str(u.id),
                                'name': u.name,
                                'slug': u_slug,
                                'bed_type': 'King Bed',
                                'base_included_adults': u.base_occupancy or 2,
                                'base_included_children': u.max_children or 1,
                                'max_adults': u.max_adults or u.max_occupancy or 3,
                                'max_children': u.max_children or 2,
                                'base_price': u_base,
                                'description': u.description or f"{u.name} at {hotel.name}",
                                'thumbnail_url': '',
                                'amenities': [],
                                'rate_plans': [
                                    {'title': 'Standard Rate', 'single_occupancy_price': u_base, 'double_occupancy_price': u_base, 'extra_adult_price': 0, 'extra_child_price': 0, 'is_popular': True}
                                ]
                            })
            except Exception as e:
                print(f"Notice: UnitType sync error: {e}")

        if custom_rooms:
            valid_slugs = []
            for rt_data in custom_rooms:
                rt_name = rt_data.get('name', 'Room')
                rt_slug = rt_data.get('slug') or re.sub(r'[^a-z0-9]+', '-', rt_name.lower()).strip('-')
                if rt_slug:
                    valid_slugs.append(rt_slug)

            if valid_slugs:
                RoomType.objects.filter(hotel=hotel).exclude(slug__in=valid_slugs).delete()

            for idx, rt_data in enumerate(custom_rooms, start=1):
                rt_name = rt_data.get('name', f'Room {idx}')
                rt_slug = rt_data.get('slug') or re.sub(r'[^a-z0-9]+', '-', rt_name.lower()).strip('-')
                if not rt_slug:
                    continue

                base_p = float(rt_data.get('basePrice') or rt_data.get('base_price') or 0.0)
                pms_room_imgs = rt_data.get('images') or rt_data.get('photos') or rt_data.get('room_images') or []
                rt_thumb = rt_data.get('thumbnailUrl') or rt_data.get('thumbnail_url') or ''
                if not rt_thumb and pms_room_imgs:
                    first_img = pms_room_imgs[0]
                    if isinstance(first_img, dict):
                        rt_thumb = first_img.get('url') or first_img.get('image_url') or first_img.get('imageUrl') or ''
                    elif isinstance(first_img, str):
                        rt_thumb = first_img

                rt, _ = RoomType.objects.get_or_create(
                    hotel=hotel,
                    slug=rt_slug,
                    defaults={
                        'name': str(rt_name)[:250],
                        'bed_type': str(rt_data.get('bedType') or rt_data.get('bed_type') or 'King Bed')[:250],
                        'max_adults': int(rt_data.get('maxAdults') or rt_data.get('max_adults') or 2),
                        'max_children': int(rt_data.get('maxChildren') or rt_data.get('max_children') or 1),
                        'base_price': base_p,
                        'description': rt_data.get('description', f'{rt_name} at {hotel.name}'),
                        'thumbnail_url': rt_thumb
                    }
                )

                rt.name = str(rt_name)[:250]
                rt.bed_type = str(rt_data.get('bedType') or rt_data.get('bed_type') or rt.bed_type or 'King Bed')[:250]
                rt.base_included_adults = int(rt_data.get('baseIncludedAdults') or rt_data.get('base_included_adults') or 2)
                rt.base_included_children = int(rt_data.get('baseIncludedChildren') or rt_data.get('base_included_children') or 1)
                rt.max_adults = int(rt_data.get('maxAdults') or rt_data.get('max_adults') or 3)
                rt.max_children = int(rt_data.get('maxChildren') or rt_data.get('max_children') or 2)
                rt.base_price = base_p
                rt.description = rt_data.get('description') or rt.description
                rt.thumbnail_url = rt_thumb
                rt.amenities = rt_data.get('amenities') or rt.amenities or []
                rt.is_active = rt_data.get('isActive', rt_data.get('is_active', True))

                # Room photos - only real photos provided
                all_room_imgs = []
                if rt_thumb:
                    all_room_imgs.append({'url': rt_thumb, 'caption': f'{rt.name} - Main View', 'image_url': rt_thumb})
                seen_r_urls = {rt_thumb} if rt_thumb else set()
                for img in pms_room_imgs:
                    if isinstance(img, dict):
                        url = img.get('url') or img.get('image_url') or img.get('imageUrl') or ''
                        cap = img.get('caption', f'{rt.name} View')
                    else:
                        url, cap = str(img), f'{rt.name} View'
                    if url and url not in seen_r_urls:
                        all_room_imgs.append({'url': url, 'image_url': url, 'caption': cap})
                        seen_r_urls.add(url)
                rt.room_images = all_room_imgs
                rt.save()

                # Rate plans for this room
                embedded_plans = rt_data.get('rate_plans') or []
                matrix_plans = rates_matrix.get(rt_data.get('id')) or rates_matrix.get(rt_slug) or rates_matrix.get(str(rt_data.get('id'))) or []
                # Prioritize matrix_plans if available as it represents explicit pricing/GST matrix configured in setup
                plans_to_sync = matrix_plans if (matrix_plans and len(matrix_plans) > 0) else embedded_plans

                if plans_to_sync:
                    plan_titles = []
                    for plan in plans_to_sync:
                        p_title = plan.get('title') or f"{plan.get('planCode', 'EP')} Rate Plan"
                        plan_titles.append(p_title)
                        s_price = float(plan.get('singlePrice') or plan.get('single_occupancy_price') or base_p)
                        
                        if plan.get('taxPct') is not None:
                            tax_pct = float(plan.get('taxPct'))
                        elif plan.get('tax_pct') is not None:
                            tax_pct = float(plan.get('tax_pct'))
                        elif plan.get('single_occupancy_tax') is not None and s_price > 0:
                            tax_pct = round((float(plan.get('single_occupancy_tax')) / s_price) * 100)
                        else:
                            tax_pct = 12.0

                        if plan.get('taxPct') is not None or plan.get('tax_pct') is not None:
                            s_tax = round(s_price * (tax_pct / 100.0), 2)
                        else:
                            s_tax = float(plan.get('single_occupancy_tax') if plan.get('single_occupancy_tax') is not None else round(s_price * (tax_pct / 100.0), 2))

                        d_price = float(plan.get('doublePrice') or plan.get('double_occupancy_price') or round(s_price * 1.2, 2))
                        if plan.get('taxPct') is not None or plan.get('tax_pct') is not None:
                            d_tax = round(d_price * (tax_pct / 100.0), 2)
                        else:
                            d_tax = float(plan.get('double_occupancy_tax') if plan.get('double_occupancy_tax') is not None else round(d_price * (tax_pct / 100.0), 2))

                        RatePlan.objects.update_or_create(
                            room_type=rt,
                            title=p_title,
                            defaults={
                                'description': plan.get('description', ''),
                                'single_occupancy_price': s_price,
                                'single_occupancy_tax': s_tax,
                                'double_occupancy_price': d_price,
                                'double_occupancy_tax': d_tax,
                                'extra_adult_price': float(plan.get('extraAdultPrice') or plan.get('extra_adult_price') or 700.0),
                                'extra_child_price': float(plan.get('extraChildPrice') or plan.get('extra_child_price') or 500.0),
                                'is_popular': plan.get('isPopular', plan.get('is_popular', False))
                            }
                        )
                    RatePlan.objects.filter(room_type=rt).exclude(title__in=plan_titles).delete()
                else:
                    p_title = 'Standard Rate'
                    extra_ad = float(rt_data.get('extraAdultPrice') or rt_data.get('extra_adult_price') or 700.0)
                    extra_ch = float(rt_data.get('extraChildPrice') or rt_data.get('extra_child_price') or 500.0)
                    RatePlan.objects.update_or_create(
                        room_type=rt,
                        title=p_title,
                        defaults={
                            'description': 'Standard room rate',
                            'single_occupancy_price': base_p,
                            'single_occupancy_tax': round(base_p * 0.12, 2),
                            'double_occupancy_price': base_p,
                            'double_occupancy_tax': round(base_p * 0.12, 2),
                            'extra_adult_price': extra_ad,
                            'extra_child_price': extra_ch,
                            'is_popular': True
                        }
                    )
                    RatePlan.objects.filter(room_type=rt).exclude(title=p_title).delete()
        else:
            # If no room types are configured in setup, remove any stale room types
            RoomType.objects.filter(hotel=hotel).delete()

        # ── Amenities Synchronization ──────────────────────────────────────────────
        pms_amenities = settings.get('amenities') or pms_p.get('amenities') or []
        if not pms_amenities:
            pms_amenities = [
                {'name': 'Free High-Speed Wi-Fi', 'icon_name': 'wifi'},
                {'name': 'Air Conditioning (AC)', 'icon_name': 'wind'},
                {'name': 'Swimming Pool & Sun Deck', 'icon_name': 'droplet'},
                {'name': 'Multi-Cuisine Fine Dining Restaurant', 'icon_name': 'utensils'},
                {'name': '24/7 Front Desk & Room Service', 'icon_name': 'clock'},
                {'name': 'Fitness Center & Gym', 'icon_name': 'activity'},
                {'name': 'Smart 4K LED Television', 'icon_name': 'tv'},
                {'name': 'Premium Ensuite Bathroom & Geyser', 'icon_name': 'thermometer'},
                {'name': 'Daily Housekeeping & Linen Care', 'icon_name': 'sparkles'},
                {'name': 'Airport & Transit Shuttle Support', 'icon_name': 'truck'},
                {'name': 'EV Charging Station', 'icon_name': 'zap'},
                {'name': 'Secure 24/7 CCTV & Parking', 'icon_name': 'shield'},
            ]
        HotelAmenity.objects.filter(hotel=hotel).delete()
        if pms_amenities and isinstance(pms_amenities, list):
            amenities_to_link = []
            for am_item in pms_amenities:
                if isinstance(am_item, dict):
                    a_name = am_item.get('name')
                    icon = am_item.get('icon_name') or am_item.get('icon') or 'sparkles'
                    enabled = am_item.get('enabled', True)
                else:
                    a_name = str(am_item)
                    icon = 'sparkles'
                    enabled = True
                if a_name and str(a_name).strip() and enabled is not False:
                    am, _ = Amenity.objects.get_or_create(name=str(a_name).strip(), defaults={'icon_name': icon})
                    amenities_to_link.append(HotelAmenity(hotel=hotel, amenity=am))
            if amenities_to_link:
                HotelAmenity.objects.bulk_create(amenities_to_link)

        # ── Policies Synchronization ───────────────────────────────────────────────
        Policy.objects.filter(hotel=hotel).delete()
        policies_data = settings.get('policies') or []
        policies_to_create = []
        if policies_data and isinstance(policies_data, list):
            for idx, pol in enumerate(policies_data, start=1):
                if isinstance(pol, dict) and pol.get('title') and pol.get('content', '').strip():
                    policies_to_create.append(
                        Policy(
                            hotel=hotel,
                            policy_type=pol.get('policy_type', 'general'),
                            title=pol['title'].strip(),
                            content=pol.get('content', '').strip(),
                            sort_order=idx
                        )
                    )
        else:
            if pms_p.get('house_rules'):
                policies_to_create.append(Policy(hotel=hotel, policy_type="house_rules", title="House Rules", content=pms_p['house_rules'], sort_order=1))
            if pms_p.get('cancellation_policy'):
                policies_to_create.append(Policy(hotel=hotel, policy_type="refund_cancellation", title="Refund & Cancellation Policy", content=pms_p['cancellation_policy'], sort_order=2))
            if pms_p.get('refund_policy'):
                policies_to_create.append(Policy(hotel=hotel, policy_type="terms", title="Terms & Conditions", content=pms_p['refund_policy'], sort_order=3))

        if policies_to_create:
            Policy.objects.bulk_create(policies_to_create)

        # ── Promo Codes Synchronization ────────────────────────────────────────────
        promos = settings.get('promos')
        if promos is not None and isinstance(promos, list):
            PromoCode.objects.filter(hotel=hotel).delete()
            promos_to_create = []
            for pr in promos:
                if isinstance(pr, dict) and pr.get('code'):
                    promos_to_create.append(
                        PromoCode(
                            hotel=hotel,
                            code=str(pr.get('code', '')).upper().strip(),
                            discount_type=pr.get('discountType') or pr.get('discount_type') or 'percentage',
                            discount_value=float(pr.get('discountValue') or pr.get('discount_value') or 10.0),
                            min_nights=int(pr.get('minNights') or pr.get('min_nights') or 1),
                            valid_from=pr.get('validFrom') or None,
                            valid_to=pr.get('validTo') or None,
                            is_active=pr.get('isActive', True)
                        )
                    )
            if promos_to_create:
                PromoCode.objects.bulk_create(promos_to_create)

        # ── Addon Packages Synchronization ─────────────────────────────────────────
        addons_data = settings.get('addons')
        if addons_data is not None and isinstance(addons_data, list):
            AddonPackage.objects.filter(hotel=hotel).delete()
            addons_to_create = []
            for add_item in addons_data:
                if isinstance(add_item, dict) and add_item.get('name'):
                    addons_to_create.append(
                        AddonPackage(
                            hotel=hotel,
                            name=add_item.get('name'),
                            category=add_item.get('category', 'Dining'),
                            charge_type=add_item.get('chargeType') or add_item.get('charge_type') or 'Per Stay',
                            price=float(add_item.get('price', 1000.0)),
                            tax_pct=float(add_item.get('taxPct') or add_item.get('tax_pct') or 18.0),
                            is_active=add_item.get('isActive', True)
                        )
                    )
            if addons_to_create:
                AddonPackage.objects.bulk_create(addons_to_create)

        # ── Payment Gateways Synchronization ───────────────────────────────────────
        gateways_data = settings.get('gateways') or settings.get('payment_gateways')
        if gateways_data and isinstance(gateways_data, list):
            PaymentGateway.objects.filter(hotel=hotel).delete()
            gateways_to_create = []
            for gw in gateways_data:
                if isinstance(gw, dict) and gw.get('provider'):
                    gateways_to_create.append(
                        PaymentGateway(
                            hotel=hotel,
                            provider=gw.get('provider'),
                            key_id=gw.get('keyId') or gw.get('key_id', ''),
                            key_secret=gw.get('keySecret') or gw.get('key_secret', ''),
                            sandbox=gw.get('sandbox', False),
                            enabled=gw.get('enabled', True),
                            pay_at_hotel=gw.get('payAtHotel') or gw.get('pay_at_hotel', False),
                            deposit_pct=float(gw.get('depositPct') or gw.get('deposit_pct') or 100.0)
                        )
                    )
            if gateways_to_create:
                PaymentGateway.objects.bulk_create(gateways_to_create)

    # Invalidate cache thoroughly
    try:
        cache.delete(f"hotel_detail_cache_{hotel.slug}")
        cache.delete(f"hotel_detail_cache_{canonical_slug}")
        cache.delete(f"hotel_detail_cache_{hotel.slug.lower()}")
        cache.delete(f"hotel_detail_cache_{canonical_slug.lower()}")
        cache.delete(f"hotel_detail_{hotel.slug}")
        cache.delete(f"hotel_detail_{canonical_slug}")
        cache.delete(f"hotel_detail_{hotel.slug.lower()}")
        cache.delete(f"hotel_detail_{canonical_slug.lower()}")
    except Exception:
        pass

    return hotel
