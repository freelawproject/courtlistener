# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0004_auto_20170901_1608'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingqueue',
            name='document_number',
            field=models.BigIntegerField(help_text='The docket entry number for the document.', null=True, blank=True),
        ),
    ]
