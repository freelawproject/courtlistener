BEGIN;
--
-- Create model EmailSent
--
CREATE TABLE "users_emailsent" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "message_id" uuid NOT NULL, "from_email" varchar(300) NOT NULL, "to" varchar(254)[] NULL, "bcc" varchar(254)[] NULL, "cc" varchar(254)[] NULL, "reply_to" varchar(254)[] NULL, "subject" text NOT NULL, "plain_text" text NOT NULL, "html_message" text NOT NULL, "headers" jsonb NULL, "user_id" integer NULL);
--
-- Create index users_email_message_f49e38_idx on field(s) message_id of model emailsent
--
CREATE INDEX "users_email_message_f49e38_idx" ON "users_emailsent" ("message_id");
ALTER TABLE "users_emailsent" ADD CONSTRAINT "users_emailsent_user_id_f9bc3e36_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "users_emailsent_date_created_4f768428" ON "users_emailsent" ("date_created");
CREATE INDEX "users_emailsent_date_modified_820cdb99" ON "users_emailsent" ("date_modified");
CREATE INDEX "users_emailsent_user_id_f9bc3e36" ON "users_emailsent" ("user_id");
COMMIT;
