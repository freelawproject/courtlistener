# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RECAPLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_started', models.DateTimeField(help_text='The moment when the scrape of the RECAP content began.')),
                ('date_completed', models.DateTimeField(help_text='The moment when the scrape of the RECAP content ended.', null=True, db_index=True, blank=True)),
                ('status', models.SmallIntegerField(help_text='The current status of the RECAP scrape.', choices=[(1, 'Scrape Completed Successfully'), (2, 'Scrape currently in progress'), (3, 'Scrape Failed')])),
            ],
        ),
    ]
