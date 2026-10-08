import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('channel_manager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaahReservationIngest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('channel_booking_id', models.CharField(db_index=True, max_length=128, unique=True)),
                ('channel_name', models.CharField(db_index=True, default='Booking.com', max_length=64)),
                ('status', models.CharField(choices=[('Synced', 'Synced'), ('Pending', 'Pending'), ('Conflict', 'Conflict'), ('Failed', 'Failed'), ('Cancelled', 'Cancelled')], default='Synced', max_length=32)),
                ('pms_booking_reference', models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ('guest_name', models.CharField(max_length=128)),
                ('guest_email', models.CharField(blank=True, default='', max_length=128)),
                ('guest_phone', models.CharField(blank=True, default='', max_length=64)),
                ('room_type_name', models.CharField(max_length=128)),
                ('check_in', models.DateField()),
                ('check_out', models.DateField()),
                ('total_amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('currency', models.CharField(default='INR', max_length=8)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('is_confirmed_to_staah', models.BooleanField(default=False)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingested_reservations', to='channel_manager.staahconfig')),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'STAAH Ingested Reservation',
                'verbose_name_plural': 'STAAH Ingested Reservations',
                'db_table': 'staah_reservation_ingest',
                'ordering': ['-created_at'],
            },
        ),
    ]
