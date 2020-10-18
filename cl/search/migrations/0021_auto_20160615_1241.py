# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0020_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text='contains the source of the Docket.', choices=[(0, 'Default'), (1, 'RECAP'), (2, 'Scraper'), (3, 'RECAP and Scraper'), (4, 'Columbia'), (6, 'Columbia and Scraper'), (5, 'Columbia and RECAP'), (7, 'Columbia, RECAP and Scraper')]),
        ),
    ]
