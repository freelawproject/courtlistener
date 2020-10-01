# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0024_add_party_info'),
        ('search', '0044_convert_pacer_document_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='parties',
            field=models.ManyToManyField(help_text=b'The parties involved in the docket', related_name='dockets', through='people_db.PartyType', to='people_db.Party', blank=True),
        ),
    ]
