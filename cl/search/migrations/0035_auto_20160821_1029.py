# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0034_auto_20160819_2141'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='cause',
            field=models.CharField(help_text='The cause for the case.', max_length=1000, blank=True),
        ),
    ]
