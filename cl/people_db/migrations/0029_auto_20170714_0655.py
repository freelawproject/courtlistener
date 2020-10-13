# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0028_auto_20170425_1120'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, help_text='The method that was used for selecting this judge for this position (generally an election or appointment).', max_length=20, choices=[('Election', (('e_part', 'Partisan Election'), ('e_non_part', 'Non-Partisan Election'))), ('Appointment', (('a_pres', 'Appointment (President)'), ('a_gov', 'Appointment (Governor)'), ('a_legis', 'Appointment (Legislature)'), ('a_judge', 'Appointment (Judge)')))]),
        ),
    ]
