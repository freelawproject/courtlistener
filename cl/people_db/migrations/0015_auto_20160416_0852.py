# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0014_auto_20160415_1116'),
    ]

    operations = [
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='political_party',
            field=models.CharField(max_length=5, choices=[('d', 'Democrat'), ('r', 'Republican'), ('i', 'Independent'), ('g', 'Green'), ('l', 'Libertarian'), ('f', 'Federalist'), ('w', 'Whig'), ('j', 'Jeffersonian Republican'), ('u', 'National Union')]),
        ),
    ]
