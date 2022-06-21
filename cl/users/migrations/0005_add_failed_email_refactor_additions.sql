BEGIN;
--
-- Create model FailedEmail
--
CREATE TABLE "users_failedemail" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "recipient" varchar(254) NOT NULL, "status" smallint NOT NULL, "next_retry_date" timestamp with time zone NULL);

--
-- Add field flag_type to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "flag_type" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "users_emailflag" ALTER COLUMN "flag_type" DROP DEFAULT;
--
-- Add field next_retry_date to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "next_retry_date" timestamp with time zone NULL;
--
-- Add field notification_subtype to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "notification_subtype" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "users_emailflag" ALTER COLUMN "notification_subtype" DROP DEFAULT;
--
-- Add field retry_counter to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "retry_counter" smallint NULL;
--
-- Alter field email_address on emailflag
--
--
-- Create constraint unique_email_ban on model emailflag
--
CREATE UNIQUE INDEX "unique_email_ban" ON "users_emailflag" ("email_address") WHERE "flag_type" = 0;
--
-- Create constraint unique_email_backoff on model emailflag
--
CREATE UNIQUE INDEX "unique_email_backoff" ON "users_emailflag" ("email_address") WHERE "flag_type" = 1;
--
-- Add field stored_email to failedemail
--
ALTER TABLE "users_failedemail" ADD COLUMN "stored_email_id" integer NOT NULL CONSTRAINT "users_failedemail_stored_email_id_cc664a91_fk_users_ema" REFERENCES "users_emailsent"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "users_failedemail_stored_email_id_cc664a91_fk_users_ema" IMMEDIATE;
--
-- Create index users_faile_recipie_c03e8d_idx on field(s) recipient of model failedemail
--
CREATE INDEX "users_faile_recipie_c03e8d_idx" ON "users_failedemail" ("recipient");
--
-- Create constraint unique_failed_enqueued on model failedemail
--
CREATE UNIQUE INDEX "unique_failed_enqueued" ON "users_failedemail" ("recipient") WHERE "status" = 1;
CREATE INDEX "users_failedemail_date_created_252c7b58" ON "users_failedemail" ("date_created");
CREATE INDEX "users_failedemail_date_modified_527ddc2c" ON "users_failedemail" ("date_modified");
CREATE INDEX "users_failedemail_stored_email_id_cc664a91" ON "users_failedemail" ("stored_email_id");
COMMIT;
