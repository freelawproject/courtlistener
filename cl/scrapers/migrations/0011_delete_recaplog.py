# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0010_allow_duplicate_pacer_doc_ids'),
    ]

    operations = [
        migrations.DeleteModel(
            name='RECAPLog',
        ),
    ]
