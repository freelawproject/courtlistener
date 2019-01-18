BEGIN;
ALTER TABLE "search_docket" ADD COLUMN "docket_number_core" varchar(20) DEFAULT '' NOT NULL;
ALTER TABLE "search_docket" ALTER COLUMN "docket_number_core" DROP DEFAULT;
ALTER TABLE "search_docket" ADD COLUMN "idb_data_id" integer NULL UNIQUE;
ALTER TABLE "search_docket" ALTER COLUMN "idb_data_id" DROP DEFAULT;
CREATE INDEX "search_docket_6c91ba55" ON "search_docket" ("docket_number_core");
CREATE INDEX "search_docket_docket_number_core_713b7b04e01f11d7_like" ON "search_docket" ("docket_number_core" varchar_pattern_ops);
ALTER TABLE "search_docket" ADD CONSTRAINT "s_idb_data_id_7696e442c56d310_fk_recap_fjcintegrateddatabase_id" FOREIGN KEY ("idb_data_id") REFERENCES "recap_fjcintegrateddatabase" ("id") DEFERRABLE INITIALLY DEFERRED;

COMMIT;
