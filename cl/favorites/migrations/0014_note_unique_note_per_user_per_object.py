from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("audio", "0012_update_source_field_noop"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("favorites", "0013_note_content_type_object_id"),
        ("search", "0059_florida_docket_entry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'CREATE UNIQUE INDEX CONCURRENTLY "unique_note_per_user_per_object" '
                'ON "favorites_note" ("content_type_id", "object_id", "user_id") '
                'WHERE "content_type_id" IS NOT NULL;'
            ),
            reverse_sql=(
                'DROP INDEX CONCURRENTLY IF EXISTS "unique_note_per_user_per_object";'
            ),
            state_operations=[
                migrations.AddConstraint(
                    model_name="note",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("content_type__isnull", False)),
                        fields=("content_type", "object_id", "user"),
                        name="unique_note_per_user_per_object",
                    ),
                ),
            ],
        ),
    ]
