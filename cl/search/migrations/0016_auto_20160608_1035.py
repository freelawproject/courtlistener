# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0015_auto_20160606_1545'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text='contains the source of the Docket.', choices=[(0, 'Default'), (1, 'RECAP'), (2, 'Scraper'), (3, 'RECAP and Scraper')]),
        ),
    ]
