from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('availability', '0007_groupblock_nationality'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupblock',
            name='room_selections',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
