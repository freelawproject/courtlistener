# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


ALTER_COLUMN = """
    BEGIN;
    ALTER TABLE
        "search_opinioncluster"
    ALTER COLUMN
        "scdb_decision_direction"
    TYPE
        integer
    USING
        scdb_decision_direction::integer;
    COMMIT;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('search', '0007_auto_20151105_0949'),
    ]

    operations = [
        migrations.RunSQL(
            ALTER_COLUMN,
            None,  # No undo.
            [
                migrations.AlterField(
                    model_name='opinioncluster',
                    name='scdb_decision_direction',
                    field=models.IntegerField(
                        blank=True,
                        help_text=b'the ideological "direction" of a decision in the Supreme Court database. More details at: http://scdb.wustl.edu/documentation.php?var=decisionDirection',
                        null=True,
                        choices=[(1, b'Conservative'),
                                 (2, b'Liberal'),
                                 (3, b'Unspecifiable')]),
                ),
            ]
        )
    ]
