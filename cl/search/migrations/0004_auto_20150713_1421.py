# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0003_add_default_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='court',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified', null=True, editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', null=True, editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='slug',
            field=models.SlugField(help_text=b'URL that the document should map to (the slug)', null=True, db_index=False),
        ),
        migrations.AlterField(
            model_name='opinion',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', null=True, editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='opinion',
            name='time_retrieved',
            field=models.DateTimeField(help_text=b'The original creation date for the item', editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='attorneys',
            field=models.TextField(default='', help_text=b'The attorneys that argued the case, as free text', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_one',
            field=models.CharField(default='', help_text=b'Primary federal citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_three',
            field=models.CharField(default='', help_text=b'Tertiary federal citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_two',
            field=models.CharField(default='', help_text=b'Secondary federal citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='judges',
            field=models.TextField(default='', help_text=b'The judges that heard the oral arguments as a simple text string. This field is used when normalized judges cannot be placed into the panel field.', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='lexis_cite',
            field=models.CharField(default='', help_text=b'Lexis Nexus citation (e.g. 1 LEXIS 38237)', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='nature_of_suit',
            field=models.TextField(default='', help_text=b'The nature of the suit. For the moment can be codes or laws or whatever', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='neutral_cite',
            field=models.CharField(default='', help_text=b'Neutral citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='posture',
            field=models.TextField(default='', help_text=b'XXX', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='procedural_history',
            field=models.TextField(default='', help_text=b'The history of the case as it jumped from court to court', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='scotus_early_cite',
            field=models.CharField(default='', help_text=b'Early SCOTUS citation such as How., Black, Cranch., etc.', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='slug',
            field=models.SlugField(help_text=b'URL that the document should map to (the slug)', null=True, db_index=False),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='specialty_cite_one',
            field=models.CharField(default='', help_text=b'Specialty citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='state_cite_one',
            field=models.CharField(default='', help_text=b'Primary state citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='state_cite_regional',
            field=models.CharField(default='', help_text=b'Regional citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='state_cite_three',
            field=models.CharField(default='', help_text=b'Tertiary state citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='state_cite_two',
            field=models.CharField(default='', help_text=b'Secondary state citation', max_length=50, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='supreme_court_db_id',
            field=models.CharField(default='', help_text=b'The ID of the item in the Supreme Court Database', max_length=10, db_index=True, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='syllabus',
            field=models.TextField(default='', help_text=b'A summary of the issues presented in the case and the outcome.', blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='westlaw_cite',
            field=models.CharField(default='', help_text=b'WestLaw citation (e.g. 22 WL 238)', max_length=50, blank=True),
            preserve_default=False,
        ),
    ]
