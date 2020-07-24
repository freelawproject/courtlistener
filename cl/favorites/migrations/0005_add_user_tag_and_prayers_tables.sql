-- Migration: Safe.

BEGIN;
--
-- Create model UserTag
--
CREATE TABLE "favorites_usertag" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "object_id" integer NOT NULL CHECK ("object_id" >= 0), "name" varchar(50) NOT NULL, "title" text NOT NULL, "description" text NOT NULL, "view_count" integer NOT NULL, "published" boolean NOT NULL, "content_type_id" integer NOT NULL, "user_id" integer NOT NULL);
--
-- Alter index_together for usertag (1 constraint(s))
--
CREATE INDEX "favorites_usertag_user_id_name_54aef6fe_idx" ON "favorites_usertag" ("user_id", "name");
--
-- Create model Prayer
--
CREATE TABLE "favorites_prayer" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "status" smallint NOT NULL, "recap_document_id" integer NOT NULL, "user_id" integer NOT NULL);
--
-- Alter index_together for prayer (3 constraint(s))
--
CREATE INDEX "favorites_prayer_recap_document_id_user_id_c5d30108_idx" ON "favorites_prayer" ("recap_document_id", "user_id");
CREATE INDEX "favorites_prayer_recap_document_id_status_82e2dbbb_idx" ON "favorites_prayer" ("recap_document_id", "status");
CREATE INDEX "favorites_prayer_date_created_user_id_status_880d7280_idx" ON "favorites_prayer" ("date_created", "user_id", "status");
ALTER TABLE "favorites_usertag" ADD CONSTRAINT "favorites_usertag_content_type_id_b7337c5e_fk_django_co" FOREIGN KEY ("content_type_id") REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "favorites_usertag" ADD CONSTRAINT "favorites_usertag_user_id_31f1221a_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "favorites_usertag_date_created_bf5fed81" ON "favorites_usertag" ("date_created");
CREATE INDEX "favorites_usertag_date_modified_1a97910d" ON "favorites_usertag" ("date_modified");
CREATE INDEX "favorites_usertag_name_f5fa2755" ON "favorites_usertag" ("name");
CREATE INDEX "favorites_usertag_name_f5fa2755_like" ON "favorites_usertag" ("name" varchar_pattern_ops);
CREATE INDEX "favorites_usertag_view_count_d653362f" ON "favorites_usertag" ("view_count");
CREATE INDEX "favorites_usertag_published_cf9b0e8c" ON "favorites_usertag" ("published");
CREATE INDEX "favorites_usertag_content_type_id_b7337c5e" ON "favorites_usertag" ("content_type_id");
CREATE INDEX "favorites_usertag_user_id_31f1221a" ON "favorites_usertag" ("user_id");
ALTER TABLE "favorites_prayer" ADD CONSTRAINT "favorites_prayer_recap_document_id_2d28d777_fk_search_re" FOREIGN KEY ("recap_document_id") REFERENCES "search_recapdocument" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "favorites_prayer" ADD CONSTRAINT "favorites_prayer_user_id_0626a4dc_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "favorites_prayer_date_created_07aee6d0" ON "favorites_prayer" ("date_created");
CREATE INDEX "favorites_prayer_recap_document_id_2d28d777" ON "favorites_prayer" ("recap_document_id");
CREATE INDEX "favorites_prayer_user_id_0626a4dc" ON "favorites_prayer" ("user_id");
COMMIT;
