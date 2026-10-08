import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0003_remove_propertycontact_property_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaahConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('domain', models.CharField(default='https://connect.su-api.com', help_text='STAAH Su API base URL', max_length=255)),
                ('app_id', models.CharField(help_text='Base64 partner app-id or domain identifier', max_length=255)),
                ('auth_token', models.CharField(help_text='Basic Auth token (e.g. Basic bkdBOGpRdEM6YkkyeVFKMno)', max_length=255)),
                ('hotel_id', models.CharField(help_text='STAAH property code / hotelid (e.g. VR-TEST)', max_length=64)),
                ('is_active', models.BooleanField(default=True, help_text='Channel Manager connection enabled')),
                ('is_live', models.BooleanField(default=False, help_text='True for production, False for sandbox simulator')),
                ('auto_sync_inventory', models.BooleanField(default=True, help_text='Automatically push ARI changes on reservation updates')),
                ('auto_fetch_reservations', models.BooleanField(default=True, help_text='Automatically poll for incoming bookings')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('property', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='staah_config', to='tenants.property')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staah_configs', to='tenants.tenant')),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Configuration',
                'verbose_name_plural': 'STAAH Configurations',
                'db_table': 'staah_config',
            },
        ),
        migrations.CreateModel(
            name='StaahSyncLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('sync_type', models.CharField(choices=[('Inventory', 'Inventory / Availability'), ('Rates', 'Rates & Pricing'), ('Restrictions', 'Restrictions (Stop-Sell / MinLOS)'), ('Reservations', 'Reservations Ingestion'), ('Content', 'Property Content'), ('Images', 'Images'), ('Mapping', 'Room & Rate Mapping'), ('Incident', 'Incident / Reporting')], max_length=32)),
                ('direction', models.CharField(choices=[('OUTBOUND', 'PMS to STAAH'), ('INBOUND', 'STAAH to PMS')], default='OUTBOUND', max_length=16)),
                ('status', models.CharField(choices=[('Success', 'Success'), ('Warning', 'Warning'), ('Error', 'Error'), ('In Progress', 'In Progress')], default='Success', max_length=16)),
                ('endpoint', models.CharField(max_length=255)),
                ('request_payload', models.JSONField(blank=True, default=dict)),
                ('response_payload', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('records_count', models.IntegerField(default=0)),
                ('duration_ms', models.IntegerField(default=0)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sync_logs', to='channel_manager.staahconfig')),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Sync Log',
                'verbose_name_plural': 'STAAH Sync Logs',
                'db_table': 'staah_sync_log',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='StaahRoomMapping',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('pms_room_code', models.CharField(db_index=True, help_text='Internal PMS room type code', max_length=64)),
                ('pms_room_name', models.CharField(help_text='Internal PMS room type display name', max_length=128)),
                ('staah_room_id', models.CharField(db_index=True, help_text='STAAH roomid', max_length=64)),
                ('staah_room_name', models.CharField(blank=True, default='', max_length=128)),
                ('status', models.CharField(choices=[('Mapped', 'Mapped'), ('Mismatch', 'Mismatch'), ('Unmapped', 'Unmapped'), ('Pending', 'Pending')], default='Mapped', max_length=24)),
                ('ota_mappings', models.JSONField(blank=True, default=dict, help_text='Channel-specific room IDs (Booking.com, Agoda, etc.)')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='room_mappings', to='channel_manager.staahconfig')),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Room Mapping',
                'verbose_name_plural': 'STAAH Room Mappings',
                'db_table': 'staah_room_mapping',
                'unique_together': {('config', 'pms_room_code')},
            },
        ),
        migrations.CreateModel(
            name='StaahRateMapping',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('pms_rate_code', models.CharField(db_index=True, help_text='Internal PMS rate plan code', max_length=64)),
                ('pms_rate_name', models.CharField(help_text='Internal PMS rate plan name', max_length=128)),
                ('meal_plan_code', models.CharField(blank=True, default='EP', help_text='EP, CP, MAP, AP, etc.', max_length=32)),
                ('staah_rate_id', models.CharField(db_index=True, help_text='STAAH rateplanid', max_length=64)),
                ('staah_rate_name', models.CharField(blank=True, default='', max_length=128)),
                ('status', models.CharField(choices=[('Mapped', 'Mapped'), ('Mismatch', 'Mismatch'), ('Unmapped', 'Unmapped'), ('Pending', 'Pending')], default='Mapped', max_length=24)),
                ('ota_mappings', models.JSONField(blank=True, default=dict, help_text='Channel-specific rate IDs')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rate_mappings', to='channel_manager.staahconfig')),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Rate Mapping',
                'verbose_name_plural': 'STAAH Rate Mappings',
                'db_table': 'staah_rate_mapping',
                'unique_together': {('config', 'pms_rate_code')},
            },
        ),
        migrations.CreateModel(
            name='StaahChannelConnection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('channel_name', models.CharField(db_index=True, max_length=64)),
                ('status', models.CharField(default='Connected', max_length=24)),
                ('property_id', models.CharField(blank=True, default='', max_length=64)),
                ('last_sync', models.CharField(blank=True, default='Just now', max_length=64)),
                ('commission', models.CharField(blank=True, default='15%', max_length=16)),
                ('bookings_mtd', models.IntegerField(default=0)),
                ('revenue_mtd', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('parity', models.CharField(default='Aligned', max_length=24)),
                ('parity_delta', models.CharField(blank=True, default='0%', max_length=32)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_connections', to='channel_manager.staahconfig')),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Channel Connection',
                'verbose_name_plural': 'STAAH Channel Connections',
                'db_table': 'staah_channel_connection',
                'unique_together': {('config', 'channel_name')},
            },
        ),
    ]
