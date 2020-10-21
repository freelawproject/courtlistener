# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0031_add_financial_disclosures'),
    ]

    operations = [
        migrations.AddField(
            model_name='partytype',
            name='date_terminated',
            field=models.DateField(help_text='The date that the party was terminated from the case, if applicable.', null=True, blank=True),
        ),
    ]
