# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0007_make_court_position_non_nullable_issue_481'),
    ]

    operations = [
        migrations.AlterField(
            model_name='court',
            name='jurisdiction',
            field=models.CharField(help_text=b'the jurisdiction of the court, one of: F (Federal Appellate), FD (Federal District), FB (Federal Bankruptcy), FBP (Federal Bankruptcy Panel), FS (Federal Special), S (State Supreme), SA (State Appellate), ST (State Trial), SS (State Special), SAG (State Attorney General), C (Committee), T (Testing)', max_length=3, choices=[(b'F', b'Federal Appellate'), (b'FD', b'Federal District'), (b'FB', b'Federal Bankruptcy'), (b'FBP', b'Federal Bankruptcy Panel'), (b'FS', b'Federal Special'), (b'S', b'State Supreme'), (b'SA', b'State Appellate'), (b'ST', b'State Trial'), (b'SS', b'State Special'), (b'SAG', b'State Attorney General'), (b'C', b'Committee'), (b'T', b'Testing')]),
        ),
    ]
