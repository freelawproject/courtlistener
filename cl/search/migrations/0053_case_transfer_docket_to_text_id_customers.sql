BEGIN;
SET CONSTRAINTS "search_casetransfer_destination_docket_i_9941948f_fk_search_do" IMMEDIATE; ALTER TABLE "search_casetransfer" DROP CONSTRAINT "search_casetransfer_destination_docket_i_9941948f_fk_search_do";
ALTER TABLE "search_casetransfer" DROP COLUMN "destination_docket_id";
--
-- Remove field origin_docket from casetransfer
--
SET CONSTRAINTS "search_casetransfer_origin_docket_id_b23a08e9_fk_search_do" IMMEDIATE; ALTER TABLE "search_casetransfer" DROP CONSTRAINT "search_casetransfer_origin_docket_id_b23a08e9_fk_search_do";
ALTER TABLE "search_casetransfer" DROP COLUMN "origin_docket_id";
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
COMMIT;
