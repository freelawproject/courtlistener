BEGIN;
--
-- Add field prayers_public to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "prayers_public" boolean DEFAULT false NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "prayers_public" DROP DEFAULT;

COMMIT;
