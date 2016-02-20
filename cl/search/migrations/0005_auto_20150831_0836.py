# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0004_auto_20150831_0810'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinioncluster',
            name='scdb_decision_direction',
            field=models.CharField(blank=True, max_length=5, null=True, help_text=b'the ideological "direction" of a decision in the Supreme Court database. More details at: http://scdb.wustl.edu/documentation.php?var=decisionDirection', choices=[(1, b'Conservative'), (2, b'Liberal'), (3, b'Unspecifiable')]),
        ),
        migrations.AddField(
            model_name='opinioncluster',
            name='scdb_votes_majority',
            field=models.IntegerField(help_text=b'the number of justices voting in the majority in a Supreme Court decision. More details at: http://scdb.wustl.edu/documentation.php?var=majVotes', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='opinioncluster',
            name='scdb_votes_minority',
            field=models.IntegerField(help_text=b'the number of justices voting in the minority in a Supreme Court decision. More details at: http://scdb.wustl.edu/documentation.php?var=minVotes', null=True, blank=True),
        ),
    ]
