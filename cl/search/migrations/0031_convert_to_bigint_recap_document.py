# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0030_convert_to_bigint'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='document_number',
            field=models.BigIntegerField(help_text='If the file is a document, the number is the document_number in RECAP docket.'),
        ),
    ]
