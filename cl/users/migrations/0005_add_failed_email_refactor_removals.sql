BEGIN;

--
-- Delete model BackoffEvent
--
DROP TABLE "users_backoffevent" CASCADE;
--
-- Remove constraint unique_email_ban from model emailflag
--
DROP INDEX IF EXISTS "unique_email_ban";
--
-- Remove field event_sub_type from emailflag
--
ALTER TABLE "users_emailflag" DROP COLUMN "event_sub_type" CASCADE;
--
-- Remove field flag from emailflag
--
ALTER TABLE "users_emailflag" DROP COLUMN "flag" CASCADE;
--
-- Remove field object_type from emailflag
--
ALTER TABLE "users_emailflag" DROP COLUMN "object_type" CASCADE;

COMMIT;
