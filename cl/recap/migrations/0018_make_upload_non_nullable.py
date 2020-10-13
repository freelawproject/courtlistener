# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0017_add_upload_type_to_pacer_html_files'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pacerhtmlfiles',
            name='upload_type',
            field=models.SmallIntegerField(default=1, help_text='The type of object that is uploaded', choices=[(1, 'HTML Docket'), (2, 'HTML attachment page'), (3, 'PDF'), (4, 'Docket history report'), (5, 'Appellate HTML docket'), (6, 'Appellate HTML attachment page')]),
            preserve_default=False,
        ),
    ]
