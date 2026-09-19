BEGIN;
--
-- Alter field content_type on floridadocument
--
ALTER TABLE "search_floridadocument" ALTER COLUMN "content_type" TYPE varchar(255);
COMMIT;
