BEGIN;
ALTER TABLE "search_opinioncluster" ADD COLUMN "harvard_id" integer NULL;
CREATE INDEX "search_opin_harvard_9f1d7e_idx" ON "search_opinioncluster" ("harvard_id");
COMMIT;
