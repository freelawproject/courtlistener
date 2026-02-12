BEGIN;
--
-- Remove field destination_docket from casetransfer
--
SET CONSTRAINTS "search_casetransfer_destination_docket_i_9941948f_fk_search_do" IMMEDIATE; ALTER TABLE "search_casetransfer" DROP CONSTRAINT "search_casetransfer_destination_docket_i_9941948f_fk_search_do";
ALTER TABLE "search_casetransfer" DROP COLUMN "destination_docket_id";
--
-- Remove field origin_docket from casetransfer
--
SET CONSTRAINTS "search_casetransfer_origin_docket_id_b23a08e9_fk_search_do" IMMEDIATE; ALTER TABLE "search_casetransfer" DROP CONSTRAINT "search_casetransfer_origin_docket_id_b23a08e9_fk_search_do";
ALTER TABLE "search_casetransfer" DROP COLUMN "origin_docket_id";
--
-- Remove field destination_docket from casetransferevent
--
ALTER TABLE "search_casetransferevent" DROP COLUMN "destination_docket_id";
--
-- Remove field origin_docket from casetransferevent
--
ALTER TABLE "search_casetransferevent" DROP COLUMN "origin_docket_id";
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
-- Add field destination_docket_number to casetransferevent
--
ALTER TABLE "search_casetransferevent" ADD COLUMN "destination_docket_number" text DEFAULT '' NOT NULL;
ALTER TABLE "search_casetransferevent" ALTER COLUMN "destination_docket_number" DROP DEFAULT;
COMMENT ON COLUMN "search_casetransferevent"."destination_docket_number" IS 'The ID of the case docket in the destination court.';
--
-- Add field origin_docket_number to casetransferevent
--
ALTER TABLE "search_casetransferevent" ADD COLUMN "origin_docket_number" text DEFAULT '' NOT NULL;
ALTER TABLE "search_casetransferevent" ALTER COLUMN "origin_docket_number" DROP DEFAULT;
COMMENT ON COLUMN "search_casetransferevent"."origin_docket_number" IS 'The ID of the docket this transfer originates from.';
--
-- Alter field url on scotusdocument
--
ALTER TABLE "search_scotusdocument" ALTER COLUMN "url" TYPE varchar(1000);
--
-- Alter field url on scotusdocumentevent
--
ALTER TABLE "search_scotusdocumentevent" ALTER COLUMN "url" TYPE varchar(1000);
--
-- Alter field url on texasdocument
--
ALTER TABLE "search_texasdocument" ALTER COLUMN "url" TYPE varchar(250);
--
-- Alter field url on texasdocumentevent
--
ALTER TABLE "search_texasdocumentevent" ALTER COLUMN "url" TYPE varchar(250);

COMMIT;
