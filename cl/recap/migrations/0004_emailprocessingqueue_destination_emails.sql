BEGIN;
--
-- Add field destination_emails to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "destination_emails" jsonb DEFAULT '[]' NOT NULL;
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "destination_emails" DROP DEFAULT;
COMMIT;
