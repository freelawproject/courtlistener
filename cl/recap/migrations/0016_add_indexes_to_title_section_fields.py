# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0015_make_pacer_case_id_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='section',
            field=models.CharField(help_text='No description provided by FJC.', max_length=200, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='subsection',
            field=models.CharField(help_text='No description provided by FJC.', max_length=200, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='title',
            field=models.TextField(help_text='No description provided by FJC.', db_index=True, blank=True),
        ),
    ]
