BEGIN;
--
-- Create model EmailFlag
--
CREATE TABLE "users_emailflag" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "email_address" varchar(254) NOT NULL, "object_type" smallint NOT NULL, "flag" smallint NULL, "event_sub_type" smallint NOT NULL);
--
-- Create index users_email_email_a_624792_idx on field(s) email_address of model emailflag
--
CREATE INDEX "users_email_email_a_624792_idx" ON "users_emailflag" ("email_address");
CREATE INDEX "users_emailflag_date_created_79b3a6a5" ON "users_emailflag" ("date_created");
CREATE INDEX "users_emailflag_date_modified_86d81fb3" ON "users_emailflag" ("date_modified");
COMMIT;
