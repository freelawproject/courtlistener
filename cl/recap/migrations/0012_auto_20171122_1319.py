# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0011_auto_20171117_1457'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingqueue',
            name='upload_type',
            field=models.SmallIntegerField(help_text='The type of object that is uploaded', choices=[(1, 'HTML Docket'), (2, 'HTML attachment page'), (3, 'PDF'), (4, 'Docket history report'), (5, 'Appellate HTML docket'), (6, 'Appellate HTML attachment page')]),
        ),
    ]
