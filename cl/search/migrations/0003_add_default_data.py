# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def set_all_to_blank(apps, schema_editor):
    OpinionCluster = apps.get_model('search', 'OpinionCluster')
    OpinionCluster.objects.filter(attorneys=None).update(attorneys='')
    OpinionCluster.objects.filter(federal_cite_one=None).update(
        federal_cite_one='')
    OpinionCluster.objects.filter(federal_cite_two=None).update(
        federal_cite_two='')
    OpinionCluster.objects.filter(federal_cite_three=None).update(
        federal_cite_three='')
    OpinionCluster.objects.filter(lexis_cite=None).update(lexis_cite='')
    OpinionCluster.objects.filter(neutral_cite=None).update(neutral_cite='')
    OpinionCluster.objects.filter(scotus_early_cite=None).update(scotus_early_cite='')
    OpinionCluster.objects.filter(specialty_cite_one=None).update(
        specialty_cite_one='')
    OpinionCluster.objects.filter(state_cite_one=None).update(
        state_cite_one='')
    OpinionCluster.objects.filter(state_cite_two=None).update(
        state_cite_two='')
    OpinionCluster.objects.filter(state_cite_three=None).update(
        state_cite_three='')
    OpinionCluster.objects.filter(state_cite_regional=None).update(
        state_cite_regional='')
    OpinionCluster.objects.filter(westlaw_cite=None).update(
        westlaw_cite='')

    OpinionCluster.objects.filter(judges=None).update(judges='')
    OpinionCluster.objects.filter(nature_of_suit=None).update(nature_of_suit='')
    OpinionCluster.objects.filter(posture=None).update(posture='')
    OpinionCluster.objects.filter(procedural_history=None).update(
        procedural_history='')
    OpinionCluster.objects.filter(supreme_court_db_id=None).update(
        supreme_court_db_id='')
    OpinionCluster.objects.filter(syllabus=None).update(
        syllabus='')

def set_all_to_null(apps, schema_editor):
    OpinionCluster = apps.get_model('search', 'OpinionCluster')
    OpinionCluster.objects.filter(attorneys='').update(attorneys=None)
    OpinionCluster.objects.filter(federal_cite_one='').update(
        federal_cite_one=None)
    OpinionCluster.objects.filter(federal_cite_two='').update(
        federal_cite_two=None)
    OpinionCluster.objects.filter(federal_cite_three='').update(
        federal_cite_three=None)
    OpinionCluster.objects.filter(lexis_cite='').update(lexis_cite=None)
    OpinionCluster.objects.filter(neutral_cite='').update(neutral_cite=None)
    OpinionCluster.objects.filter(scotus_early_cite='').update(scotus_early_cite=None)
    OpinionCluster.objects.filter(specialty_cite_one='').update(
        specialty_cite_one=None)
    OpinionCluster.objects.filter(state_cite_one='').update(
        state_cite_one=None)
    OpinionCluster.objects.filter(state_cite_two='').update(
        state_cite_two=None)
    OpinionCluster.objects.filter(state_cite_three='').update(
        state_cite_three=None)
    OpinionCluster.objects.filter(state_cite_regional='').update(
        state_cite_regional=None)
    OpinionCluster.objects.filter(westlaw_cite='').update(
        westlaw_cite=None)

    OpinionCluster.objects.filter(judges='').update(judges=None)
    OpinionCluster.objects.filter(nature_of_suit='').update(nature_of_suit=None)
    OpinionCluster.objects.filter(posture='').update(posture=None)
    OpinionCluster.objects.filter(procedural_history='').update(
        procedural_history=None)
    OpinionCluster.objects.filter(supreme_court_db_id='').update(
        supreme_court_db_id=None)
    OpinionCluster.objects.filter(syllabus='').update(
        syllabus=None)

class Migration(migrations.Migration):
    """There are a number of fields that have null=True when they should have
    it set to false, since they're text fields.

    In an ideal world, we could simply set the default data to '', and then
    we'd be off and running, but Postgresql needs the data migration to be done
    in a separate transaction than schema migration, or else it errors out with:

    django.db.utils.OperationalError: cannot ALTER TABLE "search_opinioncluster" because it has pending trigger events

    """

    dependencies = [
        ('search', '0002_load_initial_data'),
    ]

    operations = [
        migrations.RunPython(set_all_to_blank, reverse_code=set_all_to_null)
        # migrations.AlterField(
        #     model_name='court',
        #     name='date_modified',
        #     field=models.DateTimeField(
        #         help_text=b'The last moment when the item was modified',
        #         null=True, editable=False, db_index=True),
        # ),
        # migrations.AlterField(
        #     model_name='docket',
        #     name='date_modified',
        #     field=models.DateTimeField(
        #         help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown',
        #         null=True, editable=False, db_index=True),
        # ),
        # migrations.AlterField(
        #     model_name='docket',
        #     name='slug',
        #     field=models.SlugField(
        #         help_text=b'URL that the document should map to (the slug)',
        #         null=True, db_index=False),
        # ),
        # migrations.AlterField(
        #     model_name='opinion',
        #     name='date_modified',
        #     field=models.DateTimeField(
        #         help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown',
        #         null=True, editable=False, db_index=True),
        # ),
        # migrations.AlterField(
        #     model_name='opinion',
        #     name='time_retrieved',
        #     field=models.DateTimeField(
        #         help_text=b'The original creation date for the item',
        #         editable=False, db_index=True),
        # ),
        # migrations.AlterField(
        #     model_name='opinioncluster',
        #     name='date_modified',
        #     field=models.DateTimeField(
        #         help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown',
        #         editable=False, db_index=True),
        # ),
        # migrations.AlterField(
        #     model_name='opinioncluster',
        #     name='slug',
        #     field=models.SlugField(
        #         help_text=b'URL that the document should map to (the slug)',
        #         null=True, db_index=False),
        # ),

    ]
