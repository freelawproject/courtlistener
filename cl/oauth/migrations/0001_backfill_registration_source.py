"""Label the applications our DCR endpoint created before django-oauth-toolkit 3.4.

django-oauth-toolkit 3.4 added ``Application.registration_source`` and its
own migration (``oauth2_provider.0019``) only backfills it from a field that
never shipped, so every application that existed before the upgrade lands on
the ``manual`` default. Applications created through our ``/o/register/``
endpoint are the ones with no owner and ``skip_authorization`` off, the same
rule ``cl.oauth.cleanup_utils`` uses to find them, so those are relabeled
``dcr``. In-house applications have an owner or skip authorization and stay
``manual``.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps
from oauth2_provider.settings import oauth2_settings


def label_dcr_applications(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    """Set ``registration_source="dcr"`` on ownerless, consent-requiring apps."""
    Application = apps.get_model(oauth2_settings.APPLICATION_MODEL)
    Application.objects.using(schema_editor.connection.alias).filter(
        user__isnull=True,
        skip_authorization=False,
        registration_source="manual",
    ).update(registration_source="dcr")


class Migration(migrations.Migration):
    dependencies = [
        ("oauth2_provider", "0019_application_registration_source"),
    ]

    operations = [
        migrations.RunPython(
            label_dcr_applications, migrations.RunPython.noop
        ),
    ]
