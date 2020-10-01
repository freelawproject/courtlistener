# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0041_add_date_filed_is_approximate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', max_length=32, unique=True, null=True),
        ),
    ]
