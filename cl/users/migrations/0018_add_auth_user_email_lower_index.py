from django.conf import settings
from django.db import migrations

# `auth_user` belongs to django.contrib.auth, so `AddIndexConcurrently` can't
# reach it from this app: it resolves `model_name` against the migration's own
# app_label, and we can't add a `Meta.indexes` entry to Django's `User`. Raw
# SQL is the equivalent. `RunSQL` declares no state operations, so Django's
# model state stays untouched and `makemigrations` has nothing to detect.
CREATE_EMAIL_LOWER_INDEX = (
    'CREATE INDEX CONCURRENTLY "auth_user_email_lower_idx" '
    'ON "auth_user" (LOWER("email"))'
)

DROP_EMAIL_LOWER_INDEX = (
    'DROP INDEX CONCURRENTLY IF EXISTS "auth_user_email_lower_idx"'
)


class Migration(migrations.Migration):
    # PostgreSQL refuses CONCURRENTLY inside a transaction, and `auth_user` is
    # read on every authenticated request, so the lock a plain CREATE INDEX
    # takes is not an option.
    atomic = False

    dependencies = [
        ("users", "0017_allow_blank_activation_key_noop"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_EMAIL_LOWER_INDEX,
            reverse_sql=DROP_EMAIL_LOWER_INDEX,
        ),
    ]
