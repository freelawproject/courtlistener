# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0074_add_filepath_local_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='Citation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('volume', models.SmallIntegerField(help_text=b'The volume of the reporter')),
                ('reporter', models.TextField(help_text=b'The abbreviation for the reporter', db_index=True)),
                ('page', models.SmallIntegerField(help_text=b'The page of the citation in the reporter')),
                ('type', models.SmallIntegerField(help_text=b'The type of citation that this is.', choices=[(1, b'A federal reporter citation'), (2, b'A citation in a state-based reporter'), (3, b'A citation in a regional reporter'), (4, b'A citation in a specialty reporter'), (5, b'A citation in an early SCOTUS reporter, like Wheat.'), (6, b'A citation in the Lexis system'), (7, b'A citation in the WestLaw system'), (8, b'A vendor neutral citation')])),
                ('cluster', models.ForeignKey(related_name='citations', to='search.OpinionCluster', help_text=b'The cluster that the citation applies to',
                                              on_delete=models.CASCADE)),
            ],
        ),
        migrations.AlterIndexTogether(
            name='citation',
            index_together=set([('volume', 'reporter'), ('volume', 'reporter', 'page')]),
        ),
    ]
