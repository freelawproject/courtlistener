BEGIN;
--
-- Alter field filepath on financialdisclosure
--
ALTER TABLE "disclosures_financialdisclosure" ALTER COLUMN "filepath" TYPE varchar(300) USING "filepath"::varchar(300);
--
-- Alter field thumbnail on financialdisclosure
--
ALTER TABLE "disclosures_financialdisclosure" ALTER COLUMN "thumbnail" TYPE varchar(300) USING "thumbnail"::varchar(300);
COMMIT;
