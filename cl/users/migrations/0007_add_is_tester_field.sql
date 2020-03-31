BEGIN;
--
-- Add field is_tester to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "is_tester" boolean DEFAULT false NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "is_tester" DROP DEFAULT;
COMMIT;
