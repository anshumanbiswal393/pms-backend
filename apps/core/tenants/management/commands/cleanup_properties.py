import re
from django.core.management.base import BaseCommand
from apps.core.tenants.models import Tenant, Property
from apps.booking.models import Hotel

def sanitize_text(val):
    if not val:
        return val
    # Remove junk special symbols like @, #, $, %, ^, *, ~, etc. (keeping standard punctuation like . , - ' & /)
    cleaned = re.sub(r'[@#$%^*~`+=<>]+', '', str(val))
    # Replace multiple spaces with a single space
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

class Command(BaseCommand):
    help = 'Clean special characters from property data and deduplicate hotels per tenant'

    def handle(self, *args, **options):
        self.stdout.write("=== STARTING PROPERTY CLEANUP & DEDUPLICATION ===")

        # 1. Sanitize all property fields in PMS
        for prop in Property.objects.all():
            changed = False
            clean_name = sanitize_text(prop.name)
            clean_city = sanitize_text(prop.city)
            clean_state = sanitize_text(prop.state)
            clean_addr = sanitize_text(prop.address_line_1)
            
            if clean_name != prop.name:
                prop.name = clean_name
                changed = True
            if clean_city != prop.city:
                prop.city = clean_city
                changed = True
            if clean_state != prop.state:
                prop.state = clean_state
                changed = True
            if clean_addr != prop.address_line_1:
                prop.address_line_1 = clean_addr
                changed = True

            settings = prop.booking_engine_settings or {}
            if settings:
                for k in ['name', 'city', 'state', 'address', 'page_title', 'about_description']:
                    if k in settings and isinstance(settings[k], str):
                        c_val = sanitize_text(settings[k])
                        if c_val != settings[k]:
                            settings[k] = c_val
                            changed = True
                if changed:
                    prop.booking_engine_settings = settings
            
            if changed:
                prop.save()

        # 2. Deduplicate properties within each tenant
        for tenant in Tenant.objects.all():
            props = list(Property.objects.filter(tenant=tenant).order_by('-updated_at', '-created_at'))
            seen_names = {}
            seen_slugs = {}
            for p in props:
                norm_name = p.name.strip().lower()
                slug = (p.booking_engine_settings or {}).get('slug') or norm_name
                norm_slug = str(slug).strip().lower()
                
                # Check if duplicate by name or slug
                if norm_name in seen_names:
                    primary_p = seen_names[norm_name]
                    self.stdout.write(f"Deleting duplicate property ID {p.id} ('{p.name}') for tenant '{tenant.name}', keeping ID {primary_p.id}")
                    p.delete()
                elif norm_slug in seen_slugs and norm_slug not in ['hotel', 'resort', 'stay']:
                    primary_p = seen_slugs[norm_slug]
                    self.stdout.write(f"Deleting duplicate property ID {p.id} ('{p.name}') with slug '{norm_slug}' for tenant '{tenant.name}', keeping ID {primary_p.id}")
                    p.delete()
                else:
                    seen_names[norm_name] = p
                    seen_slugs[norm_slug] = p

        # 3. Sanitize Booking Hotel models
        for h in Hotel.objects.all():
            h_changed = False
            clean_h_name = sanitize_text(h.name)
            clean_h_city = sanitize_text(h.city)
            clean_h_state = sanitize_text(h.state)
            clean_h_addr = sanitize_text(h.address)
            if clean_h_name != h.name:
                h.name = clean_h_name
                h_changed = True
            if clean_h_city != h.city:
                h.city = clean_h_city
                h_changed = True
            if clean_h_state != h.state:
                h.state = clean_h_state
                h_changed = True
            if clean_h_addr != h.address:
                h.address = clean_h_addr
                h_changed = True
            if h_changed:
                h.save()

        self.stdout.write(self.style.SUCCESS(f"=== CLEANUP COMPLETE === Remaining Properties in DB: {Property.objects.count()}"))
