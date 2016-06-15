# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0013_remove_db_index_add_description_short'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='docketentry',
            options={'ordering': ('entry_number',), 'verbose_name_plural': 'Docket Entries'},
        ),
        migrations.RemoveField(
            model_name='docketentry',
            name='description_short',
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='description',
            field=models.TextField(help_text=b'The short description of the docket entry that appears on the attachments page.', blank=True),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='description',
            field=models.TextField(help_text=b'The text content of the docket entry that appears in the PACER docket page.', blank=True),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='docket',
            field=models.ForeignKey(related_name='docket_entries', to='search.Docket', help_text=b'Foreign key as a relation to the corresponding Docket object. Specifies which docket the docket entry belongs to.'),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='docket_entry',
            field=models.ForeignKey(related_name='recap_documents', to='search.DocketEntry', help_text=b'Foreign Key to the DocketEntry object to which it belongs. Multiple documents can belong to a DocketEntry. (Attachments and Documents together)'),
        ),
    ]
