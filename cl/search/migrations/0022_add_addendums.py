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
            field=models.CharField(max_length=20, choices=[(b'010combined', b'Combined Opinion'), (b'020lead', b'Lead Opinion'), (b'030concurrence', b'Concurrence'), (b'040dissent', b'Dissent'), (b'050addendum', b'Addendum')]),
        ),
    ]
