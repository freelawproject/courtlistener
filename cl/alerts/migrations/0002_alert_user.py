# -*- coding: utf-8 -*-


from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('alerts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='user',
            field=models.ForeignKey(related_name='alerts', default=1, to=settings.AUTH_USER_MODEL, help_text='The user that created the item',
                                    on_delete=models.CASCADE),
            preserve_default=False,
        ),
    ]
