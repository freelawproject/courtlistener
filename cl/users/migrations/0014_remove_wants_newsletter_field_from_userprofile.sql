BEGIN;
--
-- Remove field wants_newsletter from userprofile
--
ALTER TABLE "users_userprofile" DROP COLUMN "wants_newsletter" CASCADE;
--
-- Remove field wants_newsletter from userprofileevent
--
ALTER TABLE "users_userprofileevent" DROP COLUMN "wants_newsletter" CASCADE;
--
COMMIT;
