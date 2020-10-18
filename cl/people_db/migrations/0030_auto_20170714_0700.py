# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0029_auto_20170714_0655'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='termination_reason',
            field=models.CharField(blank=True, help_text='The reason for a termination', max_length=25, choices=[('ded', 'Death'), ('retire_vol', 'Voluntary Retirement'), ('retire_mand', 'Mandatory Retirement'), ('resign', 'Resigned'), ('other_pos', 'Appointed to Other Judgeship'), ('lost', 'Lost Election'), ('abolished', 'Court Abolished'), ('bad_judge', 'Impeached and Convicted'), ('recess_not_confirmed', 'Recess Appointment Not Confirmed'), ('termed_out', 'Term Limit Reached')]),
        ),
    ]
