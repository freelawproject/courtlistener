# Generated by Django 3.2.12 on 2022-03-18 19:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_userprofile_recap_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailFlag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The moment when the item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='The last moment when the item was modified. A value in year 1750 indicates the value is unknown')),
                ('email_address', models.EmailField(help_text='Email address flagged.', max_length=254)),
                ('object_type', models.SmallIntegerField(choices=[(0, 'Email ban'), (1, 'Email flag')], help_text='The object type assigned: ban or flag')),
                ('flag', models.SmallIntegerField(blank=True, choices=[(0, 'small_email_only'), (1, 'max_retry_reached')], help_text='The actual flag assigned, like: small_email_only', null=True)),
                ('event_sub_type', models.SmallIntegerField(choices=[(0, 'Undetermined'), (1, 'General'), (2, 'NoEmail'), (3, 'Suppressed'), (4, 'OnAccountSuppressionList'), (5, 'MailboxFull'), (6, 'MessageTooLarge'), (7, 'ContentRejected'), (8, 'AttachmentRejected'), (9, 'Complaint'), (10, 'Other')], help_text='The notification event subtype.')),
            ],
        ),
        migrations.AddIndex(
            model_name='emailflag',
            index=models.Index(fields=['email_address'], name='users_email_email_a_624792_idx'),
        ),
    ]
