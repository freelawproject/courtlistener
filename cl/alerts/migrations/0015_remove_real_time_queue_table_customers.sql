DEBUG 2025-12-04 13:51:28,954 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.007)
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
DEBUG 2025-12-04 13:51:28,955 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_sql): "(0.000) SELECT "django_migrations"."id", "django_migrations"."app", "django_migrations"."name", "django_migrations"."applied" FROM "django_migrations"; args=(); alias=default"
DEBUG 2025-12-04 13:51:28,957 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_transaction): "(0.000) BEGIN; args=None; alias=default"
DEBUG 2025-12-04 13:51:28,988 (/opt/venv/lib/python3.13/site-packages/django/db/backends/base/schema.py execute): "DROP TABLE "alerts_realtimequeue" CASCADE; (params None)"
DEBUG 2025-12-04 13:51:28,988 (/opt/venv/lib/python3.13/site-packages/django/db/backends/utils.py debug_transaction): "(0.000) COMMIT; args=None; alias=default"
BEGIN;
--
-- Delete model RealTimeQueue
--
DROP TABLE "alerts_realtimequeue" CASCADE;
COMMIT;