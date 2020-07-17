# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-07-16 20:17

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture

fixtures = ['tenn_judges']


def load_fixtures(apps, schema_editor):
    for fixture in fixtures:
        load_migration_fixture(apps, schema_editor, fixture, 'people_db')

def unload_fixture(apps, schema_editor):
    Person = apps.get_model("people_db", "Person")
    Position = apps.get_model("people_db", "Position")
    # Source = apps.get_model("people_db", "Source")
    new_pks = ['tennworkcompapp', 'tennworkcompcl']
    for pk in new_pks:
        for human in Position.objects.filter(court_id=pk):
            pers = Person.objects.get(id=human.person_id)
            human.delete()
            pers.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0042_noop_update_help_text'),
    ]

    operations = [
        migrations.RunPython(load_fixtures, unload_fixture),
    ]
