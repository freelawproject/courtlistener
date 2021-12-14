BEGIN;
--
-- Add field recap_email to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "recap_email" varchar(254) DEFAULT '' NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "recap_email" DROP DEFAULT;
COMMIT;
