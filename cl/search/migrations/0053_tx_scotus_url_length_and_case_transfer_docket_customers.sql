BEGIN;
--
-- Add field destination_docket_number to casetransfer
--
ALTER TABLE "search_casetransfer" ADD COLUMN "destination_docket_number" text DEFAULT '' NOT NULL;
ALTER TABLE "search_casetransfer" ALTER COLUMN "destination_docket_number" DROP DEFAULT;
COMMENT ON COLUMN "search_casetransfer"."destination_docket_number" IS 'The ID of the case docket in the destination court.';
--
-- Add field origin_docket_number to casetransfer
--
ALTER TABLE "search_casetransfer" ADD COLUMN "origin_docket_number" text DEFAULT '' NOT NULL;
ALTER TABLE "search_casetransfer" ALTER COLUMN "origin_docket_number" DROP DEFAULT;
COMMENT ON COLUMN "search_casetransfer"."origin_docket_number" IS 'The ID of the docket this transfer originates from.';
--
-- Alter field destination_docket on casetransfer
--
ALTER TABLE "search_casetransfer" ALTER COLUMN "destination_docket_id" TYPE integer;
COMMENT ON COLUMN "search_casetransfer"."destination_docket_id" IS 'The docket object in the destination court.';
--
-- Alter field origin_docket on casetransfer
--
ALTER TABLE "search_casetransfer" ALTER COLUMN "origin_docket_id" TYPE integer;
COMMENT ON COLUMN "search_casetransfer"."origin_docket_id" IS 'The docket object this transfer originates from.';
--
-- Alter field url on scotusdocument
--
ALTER TABLE "search_scotusdocument" ALTER COLUMN "url" TYPE varchar(1000);
--
-- Alter field url on texasdocument
--
ALTER TABLE "search_texasdocument" ALTER COLUMN "url" TYPE varchar(250);

--
-- Create constraint docket_at_least_one_fk_set on model casetransfer
--
ALTER TABLE "search_casetransfer" ADD CONSTRAINT "docket_at_least_one_fk_set" CHECK (("origin_docket_id" IS NOT NULL OR "destination_docket_id" IS NOT NULL));
COMMIT;
