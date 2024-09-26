BEGIN;
--
-- Create constraint unique_prayer_for_user_document on model prayer
--
ALTER TABLE "favorites_prayer" ADD CONSTRAINT "unique_prayer_for_user_document" UNIQUE ("user_id", "recap_document_id");
COMMIT;
