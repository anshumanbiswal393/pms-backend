import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0004_subscriptionrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='productfeature',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=12),
        ),
        migrations.AddField(
            model_name='tenantsubscription',
            name='billing_cycle',
            field=models.CharField(default='MONTHLY', max_length=32),
        ),
        migrations.AddField(
            model_name='tenantsubscription',
            name='currency',
            field=models.CharField(default='USD', max_length=3),
        ),
        migrations.AddField(
            model_name='tenantsubscription',
            name='custom_name',
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='tenantsubscription',
            name='is_custom',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenantsubscription',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=12),
        ),
        migrations.AlterField(
            model_name='tenantsubscription',
            name='plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tenant_subscriptions', to='subscriptions.subscriptionplan'),
        ),
        migrations.CreateModel(
            name='TenantSubscriptionFeature',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('feature_code', models.CharField(db_index=True, max_length=64)),
                ('price', models.DecimalField(decimal_places=2, default=0.00, max_digits=12)),
                ('is_active', models.BooleanField(default=True)),
                ('product_feature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tenant_subscription_features', to='subscriptions.productfeature')),
                ('tenant_subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='features', to='subscriptions.tenantsubscription')),
            ],
            options={
                'db_table': 'tenant_subscription_feature',
                'unique_together': {('tenant_subscription', 'product_feature')},
            },
        ),
    ]
