# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0039_add_role_raw'),
        ('search', '0065_add_og_docket_number'),
    ]

    operations = [
        migrations.RenameField(
            model_name='originatingcourtinformation',
            old_name='date_judgement',
            new_name='date_judgment',
        ),
        migrations.RenameField(
            model_name='originatingcourtinformation',
            old_name='date_judgement_oed',
            new_name='date_judgment_eod',
        ),
        migrations.AddField(
            model_name='originatingcourtinformation',
            name='ordering_judge',
            field=models.ForeignKey(related_name='+', blank=True, to='people_db.Person', help_text=b'The judge that issued the final order in the case.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='originatingcourtinformation',
            name='ordering_judge_str',
            field=models.TextField(help_text=b'The judge that issued the final order in the case, as a string.', blank=True),
        ),
    ]
