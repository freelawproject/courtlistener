BEGIN;
ALTER TABLE "search_docketentry" ADD COLUMN "pacer_sequence_number" smallint NULL;
ALTER TABLE "search_docketentry" ALTER COLUMN "pacer_sequence_number" DROP DEFAULT;
ALTER TABLE "search_docketentry" ADD COLUMN "recap_sequence_number" varchar(50) DEFAULT '' NOT NULL;
ALTER TABLE "search_docketentry" ALTER COLUMN "recap_sequence_number" DROP DEFAULT;
ALTER TABLE "search_docketentry" ALTER COLUMN "entry_number" DROP NOT NULL;
ALTER TABLE "search_recapdocument" ALTER COLUMN "document_number" SET DEFAULT '';
ALTER TABLE "search_recapdocument" ALTER COLUMN "document_number" DROP DEFAULT;
ALTER TABLE "search_docketentry" DROP CONSTRAINT "search_docketentry_docket_id_12fd448b9aa007ca_uniq";
CREATE INDEX "search_docketentry_recap_sequence_number_1c82e51988e2d89f_idx" ON "search_docketentry" ("recap_sequence_number", "entry_number");
CREATE INDEX "search_docketentry_eb19fcf7" ON "search_docketentry" ("pacer_sequence_number");
CREATE INDEX "search_docketentry_bff4d47b" ON "search_docketentry" ("recap_sequence_number");
CREATE INDEX "search_docketentry_recap_sequence_number_d700f0391e8213a_like" ON "search_docketentry" ("recap_sequence_number" varchar_pattern_ops);

COMMIT;
