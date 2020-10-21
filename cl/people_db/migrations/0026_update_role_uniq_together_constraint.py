# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0025_add_unknown_role'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='role',
            unique_together=set([('party', 'attorney', 'role', 'docket')]),
        ),
    ]
