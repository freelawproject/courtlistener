BEGIN;
--
-- Create model BackoffEvent
--
CREATE TABLE "users_backoffevent" ("id" serial NOT NULL PRIMARY KEY, "email_address" varchar(254) NOT NULL, "retry_counter" smallint NOT NULL, "next_retry_date" timestamp with time zone NOT NULL, "date_created" timestamp with time zone NOT NULL);
--
-- Create index users_backo_email_a_f71b7f_idx on field(s) email_address of model backoffevent
--
CREATE INDEX "users_backo_email_a_f71b7f_idx" ON "users_backoffevent" ("email_address");
COMMIT;
