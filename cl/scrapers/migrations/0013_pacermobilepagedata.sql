-- Migration: Safe.


BEGIN;
--
-- Create model PACERMobilePageData
--
CREATE TABLE "scrapers_pacermobilepagedata" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "date_last_mobile_crawl" timestamp with time zone NULL, "count_last_mobile_crawl" integer NULL, "count_last_rss_crawl" integer NOT NULL, "docket_id" integer NOT NULL UNIQUE);
ALTER TABLE "scrapers_pacermobilepagedata" ADD CONSTRAINT "scrapers_pacermobile_docket_id_f3963d69_fk_search_do" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "scrapers_pacermobilepagedata_date_created_79d19dab" ON "scrapers_pacermobilepagedata" ("date_created");
CREATE INDEX "scrapers_pacermobilepagedata_date_modified_0983a830" ON "scrapers_pacermobilepagedata" ("date_modified");
CREATE INDEX "scrapers_pacermobilepagedata_date_last_mobile_crawl_809860f7" ON "scrapers_pacermobilepagedata" ("date_last_mobile_crawl");
COMMIT;
