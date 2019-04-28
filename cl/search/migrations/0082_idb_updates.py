# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0024_idb_updates'),
        ('search', '0081_enlarge_pacer_sequence_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='docket_number_core',
            field=models.CharField(help_text=b'For federal district court dockets, this is the most distilled docket number available. In this field, the docket number is stripped down to only the year and serial digits, eliminating the office at the beginning, letters in the middle, and the judge at the end. Thus, a docket number like 2:07-cv-34911-MJL becomes simply 0734911. This is the format that is provided by the IDB and is useful for de-duplication types of activities which otherwise get messy. We use a char field here to preserve leading zeros.', max_length=20, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='idb_data',
            field=models.OneToOneField(related_name='docket', null=True, blank=True, to='recap.FjcIntegratedDatabase', help_text=b'Data from the FJC Integrated Database associated with this case.',
                                       on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'RECAP'), (2, b'Scraper'), (3, b'RECAP and Scraper'), (4, b'Columbia'), (6, b'Columbia and Scraper'), (5, b'Columbia and RECAP'), (7, b'Columbia, RECAP and Scraper'), (8, b'Integrated Database'), (9, b'RECAP and IDB'), (10, b'Scraper and IDB'), (11, b'RECAP, Scraper, and IDB'), (12, b'Columbia and IDB'), (13, b'Columbia, RECAP, and IDB'), (14, b'Columbia, Scraper, and IDB'), (15, b'Columbia, RECAP, Scraper, and IDB')]),
        ),
        migrations.AlterField(
            model_name='opinion',
            name='download_url',
            field=models.URLField(help_text=b'The URL where the item was originally scraped. Note that these URLs may often be dead due to the court or the bulk provider changing their website. We keep the original link here given that it often contains valuable metadata.', max_length=500, null=True, db_index=True, blank=True),
        ),
    ]
