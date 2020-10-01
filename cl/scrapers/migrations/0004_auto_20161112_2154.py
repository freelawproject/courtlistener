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
            field=models.DateTimeField(help_text=b'The moment when the scrape of the RECAP content began.', auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='recaplog',
            name='status',
            field=models.SmallIntegerField(help_text=b'The current status of the RECAP scrape.', choices=[(1, b'Scrape Completed Successfully'), (2, b'Scrape currently in progress'), (4, b'Getting list of new content from archive server'), (5, b'Successfully got the change list.'), (6, b'Getting and merging items from server'), (7, b'All changes downloaded and merged from server.'), (8, b'Extracting contents.'), (3, b'Scrape Failed')]),
        ),
    ]
