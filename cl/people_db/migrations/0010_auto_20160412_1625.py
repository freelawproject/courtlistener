# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0009_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, max_length=20, choices=[('Election', (('e_part', 'Partisan Election'), ('e_non_part', 'Non-Partisan Election'))), ('Appointment', (('a_pres', 'Appointment (President)'), ('a_gov', 'Appointment (Governor)'), ('a_legis', 'Appointment (Legislature)')))]),
        ),
    ]
