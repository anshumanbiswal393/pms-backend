from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0012_corporateaccount_address_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='held_until',
            field=models.DateTimeField(blank=True, db_index=True, help_text='Timestamp when temporary cart hold expires (default 5 min)', null=True),
        ),
        migrations.AddField(
            model_name='reservation',
            name='idempotency_key',
            field=models.CharField(blank=True, db_index=True, help_text='Unique client token preventing duplicate charges on retry', max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name='reservation',
            name='status',
            field=models.CharField(
                choices=[
                    ('INQUIRY', 'Inquiry'),
                    ('PENDING', 'Pending'),
                    ('HELD', 'Held'),
                    ('CONFIRMED', 'Confirmed'),
                    ('GUARANTEED', 'Guaranteed'),
                    ('WAITLISTED', 'Waitlisted'),
                    ('CHECKED_IN', 'Checked In'),
                    ('CHECKED_OUT', 'Checked Out'),
                    ('CANCELLED', 'Cancelled'),
                    ('NO_SHOW', 'No Show')
                ],
                default='PENDING',
                max_length=24
            ),
        ),
        migrations.RemoveConstraint(
            model_name='reservation',
            name='reservation_status_check',
        ),
        migrations.AddConstraint(
            model_name='reservation',
            constraint=models.CheckConstraint(
                condition=models.Q(('status__in', [
                    'INQUIRY', 'PENDING', 'HELD', 'CONFIRMED', 'GUARANTEED',
                    'WAITLISTED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'NO_SHOW'
                ])),
                name='reservation_status_check'
            ),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['held_until'], name='reservations_held_un_idx'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['idempotency_key'], name='reservations_idempot_idx'),
        ),
    ]
