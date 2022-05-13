BEGIN;
--
-- Add field notification_subtype to backoffevent
--
ALTER TABLE "users_backoffevent" ADD COLUMN "notification_subtype" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "users_backoffevent" ALTER COLUMN "notification_subtype" DROP DEFAULT;
--
-- Alter field email_address on backoffevent
--
--
-- Alter field email_address on emailflag
--
--
-- Alter field event_sub_type on emailflag
--
--
-- Alter field flag on emailflag
--
COMMIT;
