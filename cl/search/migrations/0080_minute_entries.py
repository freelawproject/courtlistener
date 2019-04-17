# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0079_auto_20181029_1552'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='docketentry',
            options={'ordering': ('recap_sequence_number', 'entry_number'), 'verbose_name_plural': 'Docket Entries', 'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
        migrations.AddField(
            model_name='docketentry',
            name='pacer_sequence_number',
            field=models.SmallIntegerField(help_text=b'The de_seqno value pulled out of dockets, RSS feeds, and sundry other pages in PACER. The place to find this is currently in the onclick attribute of the links in PACER. Because we do not have this value for all items in the DB, we do not use this value for anything. Still, we collect it for good measure.', null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docketentry',
            name='recap_sequence_number',
            field=models.CharField(help_text=b'A field used for ordering the docket entries on a docket. You might wonder, "Why not use the docket entry numbers?" That\'s a reasonable question, and prior to late 2018, this was the method we used. However, dockets often have "unnumbered" docket entries, and so knowing where to put those was only possible if you had another sequencing field, since they lacked an entry number. This field is populated by a combination of the date for the entry and a sequence number indicating the order that the unnumbered entries occur.', max_length=50, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='entry_number',
            field=models.BigIntegerField(help_text=b'# on the PACER docket page. For appellate cases, this may be the internal PACER ID for the document, when an entry ID is otherwise unavailable.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='document_number',
            field=models.CharField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.', max_length=32, db_index=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='docketentry',
            unique_together=set([]),
        ),
        migrations.AlterIndexTogether(
            name='docketentry',
            index_together=set([('recap_sequence_number', 'entry_number')]),
        ),
    ]
