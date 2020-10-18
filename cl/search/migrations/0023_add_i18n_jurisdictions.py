# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0022_add_addendums'),
    ]

    operations = [
        migrations.AlterField(
            model_name='court',
            name='jurisdiction',
            field=models.CharField(help_text='the jurisdiction of the court, one of: F (Federal Appellate), FD (Federal District), FB (Federal Bankruptcy), FBP (Federal Bankruptcy Panel), FS (Federal Special), S (State Supreme), SA (State Appellate), ST (State Trial), SS (State Special), SAG (State Attorney General), C (Committee), I (International), T (Testing)', max_length=3, choices=[('F', 'Federal Appellate'), ('FD', 'Federal District'), ('FB', 'Federal Bankruptcy'), ('FBP', 'Federal Bankruptcy Panel'), ('FS', 'Federal Special'), ('S', 'State Supreme'), ('SA', 'State Appellate'), ('ST', 'State Trial'), ('SS', 'State Special'), ('SAG', 'State Attorney General'), ('C', 'Committee'), ('I', 'International'), ('T', 'Testing')]),
        ),
    ]
