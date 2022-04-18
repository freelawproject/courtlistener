BEGIN;
--
-- Create model FailedEmail
--
CREATE TABLE "users_failedemail" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "message_id" uuid NOT NULL, "recipient" varchar(254) NOT NULL, "status" smallint NOT NULL, "next_retry_date" timestamp with time zone NULL);
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
COMMIT;
