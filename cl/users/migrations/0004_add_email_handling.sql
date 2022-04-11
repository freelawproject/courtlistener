BEGIN;
--
-- Create model BackoffEvent
--
CREATE TABLE "users_backoffevent" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "email_address" varchar(254) NOT NULL UNIQUE, "retry_counter" smallint NOT NULL, "next_retry_date" timestamp with time zone NOT NULL);
--
-- Create model EmailFlag
--
CREATE TABLE "users_emailflag" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "email_address" varchar(254) NOT NULL, "object_type" smallint NOT NULL, "flag" smallint NULL, "event_sub_type" smallint NOT NULL);
--
-- Create model EmailSent
--
CREATE TABLE "users_emailsent" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "message_id" uuid NOT NULL, "from_email" varchar(300) NOT NULL, "to" varchar(254)[] NULL, "bcc" varchar(254)[] NULL, "cc" varchar(254)[] NULL, "reply_to" varchar(254)[] NULL, "subject" text NOT NULL, "plain_text" text NOT NULL, "html_message" text NOT NULL, "headers" jsonb NULL, "user_id" integer NULL);
--
-- Create index users_email_email_a_624792_idx on field(s) email_address of model emailflag
--
CREATE INDEX "users_email_email_a_624792_idx" ON "users_emailflag" ("email_address");
--
-- Create constraint unique_email_ban on model emailflag
--
CREATE UNIQUE INDEX "unique_email_ban" ON "users_emailflag" ("email_address") WHERE "object_type" = 0;
--
-- Create index users_email_message_f49e38_idx on field(s) message_id of model emailsent
--
CREATE INDEX "users_email_message_f49e38_idx" ON "users_emailsent" ("message_id");
CREATE INDEX "users_backoffevent_date_created_ee8b632d" ON "users_backoffevent" ("date_created");
CREATE INDEX "users_backoffevent_date_modified_413b2021" ON "users_backoffevent" ("date_modified");
CREATE INDEX "users_backoffevent_email_address_70762f66_like" ON "users_backoffevent" ("email_address" varchar_pattern_ops);
CREATE INDEX "users_emailflag_date_created_79b3a6a5" ON "users_emailflag" ("date_created");
CREATE INDEX "users_emailflag_date_modified_86d81fb3" ON "users_emailflag" ("date_modified");
ALTER TABLE "users_emailsent" ADD CONSTRAINT "users_emailsent_user_id_f9bc3e36_fk_auth_user_id" FOREIGN KEY ("user_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "users_emailsent_date_created_4f768428" ON "users_emailsent" ("date_created");
CREATE INDEX "users_emailsent_date_modified_820cdb99" ON "users_emailsent" ("date_modified");
CREATE INDEX "users_emailsent_user_id_f9bc3e36" ON "users_emailsent" ("user_id");
COMMIT;
