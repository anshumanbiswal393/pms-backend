from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0011_posaudittrail_posbankaccount_posbillergroup_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='posoutletconfig',
            name='billing_preferences',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='posoutletconfig',
            name='integrations',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='posoutletconfig',
            name='service_mode',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='posoutletconfig',
            name='step_status',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
