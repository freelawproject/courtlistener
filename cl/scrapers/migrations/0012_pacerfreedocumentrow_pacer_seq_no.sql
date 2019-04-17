BEGIN;
ALTER TABLE "scrapers_pacerfreedocumentrow" ADD COLUMN "pacer_seq_no" integer NULL;
ALTER TABLE "scrapers_pacerfreedocumentrow" ALTER COLUMN "pacer_seq_no" DROP DEFAULT;

COMMIT;
