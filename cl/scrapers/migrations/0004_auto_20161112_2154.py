# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0003_load_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recaplog',
            name='date_started',
            field=models.DateTimeField(help_text='The moment when the scrape of the RECAP content began.', auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='recaplog',
            name='status',
            field=models.SmallIntegerField(help_text='The current status of the RECAP scrape.', choices=[(1, 'Scrape Completed Successfully'), (2, 'Scrape currently in progress'), (4, 'Getting list of new content from archive server'), (5, 'Successfully got the change list.'), (6, 'Getting and merging items from server'), (7, 'All changes downloaded and merged from server.'), (8, 'Extracting contents.'), (3, 'Scrape Failed')]),
        ),
    ]
