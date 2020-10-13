# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0014_add_pq_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingqueue',
            name='pacer_case_id',
            field=models.CharField(help_text='The cased ID provided by PACER.', max_length=100, db_index=True, blank=True),
        ),
    ]
