# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0006_auto_20160416_0852'),
    ]

    operations = [
        migrations.AlterField(
            model_name='court',
            name='position',
            field=models.FloatField(default=0, help_text='A dewey-decimal-style numeral indicating a hierarchical ordering of jurisdictions', unique=True, db_index=True),
            preserve_default=False,
        ),
    ]
