# -*- coding: utf-8 -*-


import sys

from django.db import migrations, models

from cl.lib.migration_utils import load_migration_fixture


"""

POST-FIXTURE TODO: After loading of the governors, you will need to manually create
aliases for five of the "people" below using the admin panel.
Substitute the relevant alias pk in the "is_alias_of" field

"""


def load_fixture(apps, schema_editor):
    """Noop"""

    # Previously, this ran the code below, but to slim down the repo and to
    # simplify our lives, I'm commenting it out and yanking the files.

    #load_migration_fixture(apps, schema_editor, "ca_govs", "people_db")

    # Do positions
    # TODO POST-IMPORTATION:
    # Import Positions for Earl Warren and Ronald Reagan
    # Since these entities already exists in the db, but they are
    # not present in the fixtures, we can't import their positions here.
    # You will need to manually add the two positions at the bottom to the db
    # using the admin panel
    # load_migration_fixture(
    #     apps, schema_editor, "ca_govs_positions", "people_db"
    # )


def unload_fixture(apps, schema_editor):
    """Noop"""
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("people_db", "0003_load_schools_and_races"),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]


WARREN_CA_GOV_POSITION = {
    "fields": {
        "position_type": "gov",
        "job_title": "Governor",
        "date_start": "1943-01-04",
        "date_termination": "1953-10-05",
        "organization_name": "State of California",
        "person": "464",
        "supervisor": "null",
        "date_referred_to_judicial_committee": "null",
        "votes_no": "null",
        "date_granularity_start": "%Y-%m-%d",
        "date_hearing": "null",
        "court": "null",
        "votes_yes": "null",
        "date_retirement": "null",
        "date_elected": "null",
        "predecessor": "null",
        "termination_reason": "",
        "appointer": "null",
        "judicial_committee_action": "",
        "date_granularity_termination": "",
        "date_confirmation": "null",
        "school": "null",
        "date_judicial_committee_action": "null",
        "date_modified": "2021-09-13T18:35:56.249Z",
        "voice_vote": "null",
        "how_selected": "",
        "date_created": "2021-09-13T18:35:56.249Z",
        "date_nominated": "null",
        "nomination_process": "",
        "date_recess_appointment": "null",
    },
    "model": "people_db.position",
    "pk": "null",
}

REAGAN_CA_GOV_POSITION = {
    "fields": {
        "position_type": "gov",
        "job_title": "Governor",
        "date_start": "1967-01-02",
        "date_termination": "1975-01-06",
        "organization_name": "State of California",
        "person": "39",
        "supervisor": "null",
        "date_referred_to_judicial_committee": "null",
        "votes_no": "null",
        "date_granularity_start": "%Y-%m-%d",
        "date_hearing": "null",
        "court": "null",
        "votes_yes": "null",
        "date_retirement": "null",
        "date_elected": "null",
        "predecessor": "null",
        "termination_reason": "",
        "appointer": "null",
        "judicial_committee_action": "",
        "date_granularity_termination": "",
        "date_confirmation": "null",
        "school": "null",
        "date_judicial_committee_action": "null",
        "date_modified": "2021-09-13T18:35:56.249Z",
        "voice_vote": "null",
        "how_selected": "",
        "date_created": "2021-09-13T18:35:56.249Z",
        "date_nominated": "null",
        "nomination_process": "",
        "date_recess_appointment": "null",
    },
    "model": "people_db.position",
    "pk": "null",
}
