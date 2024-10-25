BEGIN;
ALTER TABLE "search_opinioncluster" ADD COLUMN "harvard_id" varchar DEFAULT '0' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "harvard_id" DROP DEFAULT;
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "harvard_id" varchar DEFAULT '0' NOT NULL;
ALTER TABLE "search_opinionclusterevent" ALTER COLUMN "harvard_id" DROP DEFAULT;
CREATE INDEX "search_opinioncluster_harvard_id_b7c3eb52" ON "search_opinioncluster" ("harvard_id");
CREATE INDEX "search_opinioncluster_harvard_id_b7c3eb52_like" ON "search_opinioncluster" ("harvard_id" varchar_pattern_ops);
COMMIT;
