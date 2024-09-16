BEGIN;
--
-- Add field neon_account_id to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "neon_account_id" varchar DEFAULT '' NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "neon_account_id" DROP DEFAULT;

COMMIT;
