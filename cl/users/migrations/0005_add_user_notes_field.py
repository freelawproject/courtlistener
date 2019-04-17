# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_make_recap_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='notes',
            field=models.TextField(help_text=b'Any notes about the user.', blank=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='avatar',
            field=models.ImageField(help_text=b"the user's avatar", upload_to=b'avatars/%Y/%m/%d', blank=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='email_confirmed',
            field=models.BooleanField(default=False, help_text=b'The user has confirmed their email address'),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='employer',
            field=models.CharField(help_text=b"the user's employer", max_length=100, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='key_expires',
            field=models.DateTimeField(help_text=b"The time and date when the user's activation_key expires", null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='plaintext_preferred',
            field=models.BooleanField(default=False, help_text=b'should the alert should be sent in plaintext'),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='wants_newsletter',
            field=models.BooleanField(default=False, help_text=b'This user wants newsletters'),
        ),
    ]
