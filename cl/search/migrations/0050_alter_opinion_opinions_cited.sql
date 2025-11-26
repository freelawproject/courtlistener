System check identified some issues:

WARNINGS:
[33;1m<django.template.backends.django.DjangoTemplates object at 0x710ff4b91d30>: (templates.W003) 'auth' is used for multiple template tag modules: 'cl.custom_filters.templatetags.auth', 'django.contrib.auth.templatetags.auth'[0m
DEBUG 2025-12-26 14:48:03,675 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.002) SELECT oid, typarray FROM pg_type WHERE typname = 'hstore'; args=('hstore',); alias=default"
DEBUG 2025-12-26 14:48:03,676 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.000) SELECT oid, typarray FROM pg_type WHERE typname = 'citext'; args=('citext',); alias=default"
DEBUG 2025-12-26 14:48:03,710 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.034) 
            SELECT
                c.relname,
                CASE
                    WHEN c.relispartition THEN 'p'
                    WHEN c.relkind IN ('m', 'v') THEN 'v'
                    ELSE 't'
                END,
                obj_description(c.oid, 'pg_class')
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('f', 'm', 'p', 'r', 'v')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
        ; args=None; alias=default"
DEBUG 2025-12-26 14:48:03,712 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.001) SELECT "django_migrations"."id", "django_migrations"."app", "django_migrations"."name", "django_migrations"."applied" FROM "django_migrations"; args=(); alias=default"
DEBUG 2025-12-26 14:48:03,719 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_transaction): "(0.000) BEGIN; args=None; alias=default"
DEBUG 2025-12-26 14:48:03,945 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_transaction): "(0.000) COMMIT; args=None; alias=default"
BEGIN;
--
-- Alter field opinions_cited on opinion
--
-- (no-op)
COMMIT;
