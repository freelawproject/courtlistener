BEGIN;
--
-- Add field auto_subscribe to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "auto_subscribe" boolean DEFAULT false NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "auto_subscribe" DROP DEFAULT;
COMMIT;
