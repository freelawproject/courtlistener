BEGIN;
--
-- Create model EmailFlag
--
CREATE TABLE "users_emailflag" ("id" serial NOT NULL PRIMARY KEY, "email_address" varchar(254) NOT NULL, "flag_type" varchar(5) NOT NULL, "flag" varchar(25) NOT NULL, "reason" varchar(50) NOT NULL, "date_created" timestamp with time zone NOT NULL);
--
-- Create index users_email_email_a_624792_idx on field(s) email_address of model emailflag
--
CREATE INDEX "users_email_email_a_624792_idx" ON "users_emailflag" ("email_address");
COMMIT;
