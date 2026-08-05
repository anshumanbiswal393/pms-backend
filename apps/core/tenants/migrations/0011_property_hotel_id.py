import random
from django.db import migrations, models

def populate_hotel_ids(apps, schema_editor):
    Property = apps.get_model('tenants', 'Property')
    existing = set(Property.objects.exclude(hotel_id__isnull=True).exclude(hotel_id='').values_list('hotel_id', flat=True))
    
    for prop in Property.objects.filter(models.Q(hotel_id__isnull=True) | models.Q(hotel_id='')):
        while True:
            candidate = str(random.randint(10000, 99999))
            if candidate not in existing:
                existing.add(candidate)
                prop.hotel_id = candidate
                prop.save(update_fields=['hotel_id'])
                break

class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0010_alter_property_google_map_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='property',
            name='hotel_id',
            field=models.CharField(blank=True, db_index=True, max_length=5, null=True, unique=True),
        ),
        migrations.RunPython(populate_hotel_ids, reverse_code=migrations.RunPython.noop),
    ]
