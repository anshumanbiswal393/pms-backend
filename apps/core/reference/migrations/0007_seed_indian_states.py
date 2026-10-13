from django.db import migrations

INDIAN_STATES = [
    ("AN", "Andaman and Nicobar Islands"),
    ("AP", "Andhra Pradesh"),
    ("AR", "Arunachal Pradesh"),
    ("AS", "Assam"),
    ("BR", "Bihar"),
    ("CH", "Chandigarh"),
    ("CG", "Chhattisgarh"),
    ("DN", "Dadra and Nagar Haveli and Daman and Diu"),
    ("DL", "Delhi"),
    ("GA", "Goa"),
    ("GJ", "Gujarat"),
    ("HR", "Haryana"),
    ("HP", "Himachal Pradesh"),
    ("JK", "Jammu and Kashmir"),
    ("JH", "Jharkhand"),
    ("KA", "Karnataka"),
    ("KL", "Kerala"),
    ("LA", "Ladakh"),
    ("LD", "Lakshadweep"),
    ("MP", "Madhya Pradesh"),
    ("MH", "Maharashtra"),
    ("MN", "Manipur"),
    ("ML", "Meghalaya"),
    ("MZ", "Mizoram"),
    ("NL", "Nagaland"),
    ("OD", "Odisha"),
    ("PY", "Puducherry"),
    ("PB", "Punjab"),
    ("RJ", "Rajasthan"),
    ("SK", "Sikkim"),
    ("TN", "Tamil Nadu"),
    ("TS", "Telangana"),
    ("TR", "Tripura"),
    ("UP", "Uttar Pradesh"),
    ("UK", "Uttarakhand"),
    ("WB", "West Bengal"),
]

def seed_states(apps, schema_editor):
    Country = apps.get_model('reference', 'Country')
    State = apps.get_model('reference', 'State')

    india = Country.objects.filter(name__iexact='India').first()
    if not india:
        india = Country.objects.filter(code__iexact='IN').first()
    if not india:
        india = Country.objects.create(name='India', code='IN', phone_code='+91', is_active=True)

    for code, name in INDIAN_STATES:
        state_obj = State.objects.filter(country=india, code=code).first()
        if not state_obj:
            state_obj = State.objects.filter(country=india, name__iexact=name).first()
        if state_obj:
            state_obj.name = name
            state_obj.code = code
            state_obj.is_active = True
            state_obj.save()
        else:
            State.objects.create(country=india, code=code, name=name, is_active=True)

def reverse_seed(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('reference', '0006_eventtype_venue'),
    ]

    operations = [
        migrations.RunPython(seed_states, reverse_seed),
    ]
