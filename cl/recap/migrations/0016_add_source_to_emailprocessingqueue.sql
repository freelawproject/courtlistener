BEGIN;
--
-- Add field source to emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ADD COLUMN "source" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "source" DROP DEFAULT;
COMMENT ON COLUMN "recap_emailprocessingqueue"."source" IS 'The source of this email notification.';
--
-- Alter field court on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "court_id" TYPE varchar(15);
COMMENT ON COLUMN "recap_emailprocessingqueue"."court_id" IS 'The court where the upload was from.';
--
-- Alter field destination_emails on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "destination_emails" TYPE jsonb;
COMMENT ON COLUMN "recap_emailprocessingqueue"."destination_emails" IS 'The emails that received the notification.';
--
-- Alter field filepath on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "filepath" TYPE varchar(300);
COMMENT ON COLUMN "recap_emailprocessingqueue"."filepath" IS 'The S3 filepath to the email and receipt stored as JSON text.';
--
-- Alter field message_id on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "message_id" TYPE text;
COMMENT ON COLUMN "recap_emailprocessingqueue"."message_id" IS 'The S3 message identifier, used to pull the file in the processing tasks.';
--
-- Alter field recap_documents on emailprocessingqueue
--
-- (no-op)
--
-- Alter field status_message on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "status_message" TYPE text;
COMMENT ON COLUMN "recap_emailprocessingqueue"."status_message" IS 'Any errors that occurred while processing an item.';
--
-- Alter field uploader on emailprocessingqueue
--
ALTER TABLE "recap_emailprocessingqueue" ALTER COLUMN "uploader_id" TYPE integer;
COMMENT ON COLUMN "recap_emailprocessingqueue"."uploader_id" IS 'The user that sent in the email for processing.';
COMMIT;
