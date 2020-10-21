# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0059_allow_duplicate_pacer_doc_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='date_last_index',
            field=models.DateTimeField(help_text='The last moment that the item was indexed in Solr.', null=True, blank=True),
        ),
    ]
