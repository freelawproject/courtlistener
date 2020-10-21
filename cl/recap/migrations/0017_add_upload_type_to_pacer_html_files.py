# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0016_add_indexes_to_title_section_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='pacerhtmlfiles',
            name='upload_type',
            field=models.SmallIntegerField(help_text='The type of object that is uploaded', null=True, choices=[(1, 'HTML Docket'), (2, 'HTML attachment page'), (3, 'PDF'), (4, 'Docket history report'), (5, 'Appellate HTML docket'), (6, 'Appellate HTML attachment page')]),
        ),
    ]
