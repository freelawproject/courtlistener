# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0026_auto_20160629_1355'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_one',
            field=models.CharField(help_text='Primary federal citation', max_length=50, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_three',
            field=models.CharField(help_text='Tertiary federal citation', max_length=50, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_two',
            field=models.CharField(help_text='Secondary federal citation', max_length=50, db_index=True, blank=True),
        ),
    ]
