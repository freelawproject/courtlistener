# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0004_auto_20161112_2154'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recaplog',
            name='status',
            field=models.SmallIntegerField(help_text='The current status of the RECAP scrape.', choices=[(1, 'Scrape Completed Successfully'), (2, 'Scrape currently in progress'), (4, 'Getting list of new content from archive server'), (5, 'Successfully got the change list.'), (6, 'Getting and merging items from server'), (3, 'Scrape Failed')]),
        ),
    ]
