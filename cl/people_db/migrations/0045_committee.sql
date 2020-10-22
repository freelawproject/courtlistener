DEBUG (0.001) SELECT "search_court"."citation_string", "search_court"."id" FROM "search_court" ORDER BY "search_court"."position" ASC; args=()
DEBUG (0.002)
            SELECT c.relname, c.relkind
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'v')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid); args=None
DEBUG (0.000) SELECT "django_migrations"."app", "django_migrations"."name" FROM "django_migrations"; args=()
DEBUG CREATE TABLE "people_db_committee" ("id" serial NOT NULL PRIMARY KEY, "committee_uniq_id" varchar(9) NOT NULL, "committee_name" varchar(200) NOT NULL, "committee_party" varchar(3) NOT NULL, "candidate_id" varchar(9) NOT NULL, "connected_org_name" varchar(200) NOT NULL, "committee_type" varchar(1) NOT NULL, "committee_designation" varchar(1) NOT NULL, "org_type" varchar(1) NOT NULL); (params None)
DEBUG CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba" ON "people_db_committee" ("committee_uniq_id"); (params ())
DEBUG CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba_like" ON "people_db_committee" ("committee_uniq_id" varchar_pattern_ops); (params ())
BEGIN;
--
-- Create model Committee
--
CREATE TABLE "people_db_committee" ("id" serial NOT NULL PRIMARY KEY, "committee_uniq_id" varchar(9) NOT NULL, "committee_name" varchar(200) NOT NULL, "committee_party" varchar(3) NOT NULL, "candidate_id" varchar(9) NOT NULL, "connected_org_name" varchar(200) NOT NULL, "committee_type" varchar(1) NOT NULL, "committee_designation" varchar(1) NOT NULL, "org_type" varchar(1) NOT NULL);
CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba" ON "people_db_committee" ("committee_uniq_id");
CREATE INDEX "people_db_committee_committee_uniq_id_9693dcba_like" ON "people_db_committee" ("committee_uniq_id" varchar_pattern_ops);
COMMIT;
