BEGIN;
--
-- Remove index users_backo_email_a_f71b7f_idx from backoffevent
--
DROP INDEX IF EXISTS "users_backo_email_a_f71b7f_idx";
--
-- Alter field email_address on backoffevent
--
ALTER TABLE "users_backoffevent" ADD CONSTRAINT "users_backoffevent_email_address_70762f66_uniq" UNIQUE ("email_address");
CREATE INDEX "users_backoffevent_email_address_70762f66_like" ON "users_backoffevent" ("email_address" varchar_pattern_ops);
--
-- Create constraint unique_email_ban on model emailflag
--
CREATE UNIQUE INDEX "unique_email_ban" ON "users_emailflag" ("email_address") WHERE "object_type" = 0;
COMMIT;
