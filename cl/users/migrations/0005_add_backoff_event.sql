BEGIN;
--
-- Create model BackoffEvent
--
CREATE TABLE "users_backoffevent" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "email_address" varchar(254) NOT NULL, "retry_counter" smallint NOT NULL, "next_retry_date" timestamp with time zone NOT NULL);
--
-- Create index users_backo_email_a_f71b7f_idx on field(s) email_address of model backoffevent
--
CREATE INDEX "users_backo_email_a_f71b7f_idx" ON "users_backoffevent" ("email_address");
CREATE INDEX "users_backoffevent_date_created_ee8b632d" ON "users_backoffevent" ("date_created");
CREATE INDEX "users_backoffevent_date_modified_413b2021" ON "users_backoffevent" ("date_modified");
COMMIT;
