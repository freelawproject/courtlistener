# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0021_auto_20160615_1241'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinion',
            name='type',
            field=models.CharField(max_length=20, choices=[('010combined', 'Combined Opinion'), ('020lead', 'Lead Opinion'), ('030concurrence', 'Concurrence'), ('040dissent', 'Dissent'), ('050addendum', 'Addendum')]),
        ),
    ]
