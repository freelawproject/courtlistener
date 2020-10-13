# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0038_auto_20160906_1613'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='precedential_status',
            field=models.CharField(blank=True, help_text='The precedential status of document, one of: Published, Unpublished, Errata, Separate, In-chambers, Relating-to, Unknown', max_length=50, db_index=True, choices=[('Published', 'Precedential'), ('Unpublished', 'Non-Precedential'), ('Errata', 'Errata'), ('Separate', 'Separate Opinion'), ('In-chambers', 'In-chambers'), ('Relating-to', 'Relating-to orders'), ('Unknown', 'Unknown Status')]),
        ),
    ]
