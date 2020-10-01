# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0035_add_extra_info_to_party_type'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='party',
            unique_together=set([]),
        ),
    ]
