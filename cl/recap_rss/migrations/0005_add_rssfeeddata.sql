-- Migration: Safe.


BEGIN;
--
-- Create model RssFeedData
--
CREATE TABLE "recap_rss_rssfeeddata" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "filepath" varchar(150) NOT NULL, "court_id" varchar(15) NOT NULL);
ALTER TABLE "recap_rss_rssfeeddata" ADD CONSTRAINT "recap_rss_rssfeeddata_court_id_8bd4988e_fk_search_court_id" FOREIGN KEY ("court_id") REFERENCES "search_court" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "recap_rss_rssfeeddata_date_created_0b97403f" ON "recap_rss_rssfeeddata" ("date_created");
CREATE INDEX "recap_rss_rssfeeddata_date_modified_cfe95447" ON "recap_rss_rssfeeddata" ("date_modified");
CREATE INDEX "recap_rss_rssfeeddata_court_id_8bd4988e" ON "recap_rss_rssfeeddata" ("court_id");
CREATE INDEX "recap_rss_rssfeeddata_court_id_8bd4988e_like" ON "recap_rss_rssfeeddata" ("court_id" varchar_pattern_ops);
COMMIT;
