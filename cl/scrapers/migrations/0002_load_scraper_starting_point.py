import sys

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture


def load_fixture(apps, schema_editor):
    if 'test' not in sys.argv:
        fixture = 'pacer_free_docs_initial_data'
        load_migration_fixture(apps, schema_editor, fixture, 'scrapers')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    RECAPLog = apps.get_model("scrapers", "RECAPLog")
    RECAPLog.objects.all().delete()

    PACERFreeDocumentLog = apps.get_model("scrapers", "PACERFreeDocumentLog")
    PACERFreeDocumentLog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0001_initial'),
        ("search", "0002_load_initial_data"),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture)
    ]
