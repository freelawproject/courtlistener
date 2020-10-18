# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0021_auto_20180605_2126'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pacerhtmlfiles',
            name='upload_type',
            field=models.SmallIntegerField(help_text='The type of object that is uploaded', choices=[(1, 'HTML Docket'), (2, 'HTML attachment page'), (3, 'PDF'), (4, 'Docket history report'), (5, 'Appellate HTML docket'), (6, 'Appellate HTML attachment page'), (7, 'Internet Archive XML docket'), (8, 'Case report (iquery.pl) page')]),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='upload_type',
            field=models.SmallIntegerField(help_text='The type of object that is uploaded', choices=[(1, 'HTML Docket'), (2, 'HTML attachment page'), (3, 'PDF'), (4, 'Docket history report'), (5, 'Appellate HTML docket'), (6, 'Appellate HTML attachment page'), (7, 'Internet Archive XML docket'), (8, 'Case report (iquery.pl) page')]),
        ),
    ]
