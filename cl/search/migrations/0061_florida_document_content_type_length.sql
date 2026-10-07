BEGIN;
--
-- Alter field content_type on floridadocument
--
ALTER TABLE "search_floridadocument" ALTER COLUMN "content_type" TYPE varchar(255);
--
-- Alter field content_type on floridadocumentevent
--
ALTER TABLE "search_floridadocumentevent" ALTER COLUMN "content_type" TYPE varchar(255);
COMMIT;
