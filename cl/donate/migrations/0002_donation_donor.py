# -*- coding: utf-8 -*-


from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('donate', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='donation',
            name='donor',
            field=models.ForeignKey(related_name='donations', default=1, to=settings.AUTH_USER_MODEL, help_text='The user that made the donation',
                                    on_delete=models.CASCADE),
            preserve_default=False,
        ),
    ]
