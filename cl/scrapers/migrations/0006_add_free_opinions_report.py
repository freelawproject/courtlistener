# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0045_add_party_info'),
        ('scrapers', '0005_update_scrape_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='PACERFreeDocumentLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_started', models.DateTimeField(help_text='The moment when the scrape of the RECAP content began.', auto_now_add=True)),
                ('date_completed', models.DateTimeField(help_text='The moment when the scrape of the RECAP content ended.', null=True, db_index=True, blank=True)),
                ('date_queried', models.DateField(help_text='The date that was queried.', db_index=True)),
                ('status', models.SmallIntegerField(help_text='The status of the scrape.', choices=[(1, 'Scrape completed successfully'), (2, 'Scrape currently in progress'), (3, 'Scrape failed')])),
                ('court', models.ForeignKey(help_text='The court where items were being downloaded from.', to='search.Court',
                                            on_delete=models.CASCADE)),
            ],
        ),
    ]
