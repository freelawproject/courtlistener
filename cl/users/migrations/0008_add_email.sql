BEGIN;
--
-- Create model Email
--
CREATE TABLE "users_email" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "message_id" uuid NOT NULL, "from_email" varchar(254) NOT NULL, "to" varchar(254) NULL, "bcc" varchar(254) NULL, "cc" varchar(254) NULL, "subject" varchar(989) NOT NULL, "message" text NOT NULL, "html_message" text NOT NULL, "headers" jsonb NULL, "user_id" integer NULL);
--
-- Create index users_email_message_a1dc22_idx on field(s) message_id of model email
--
CREATE INDEX "users_email_message_a1dc22_idx" ON "users_email" ("message_id");
ALTER TABLE "users_email" ADD CONSTRAINT "users_email_user_id_d0a90c30_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "users_email_date_created_f7257b1f" ON "users_email" ("date_created");
CREATE INDEX "users_email_date_modified_f19b93d8" ON "users_email" ("date_modified");
CREATE INDEX "users_email_user_id_d0a90c30" ON "users_email" ("user_id");
COMMIT;
