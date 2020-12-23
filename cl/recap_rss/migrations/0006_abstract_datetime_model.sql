BEGIN;
--
-- Alter field date_created on rssfeeddata
--
ALTER TABLE "recap_rss_rssfeeddata" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:39.596684+00:00'::timestamptz;
ALTER TABLE "recap_rss_rssfeeddata" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on rssfeeddata
--
ALTER TABLE "recap_rss_rssfeeddata" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:39.617653+00:00'::timestamptz;
ALTER TABLE "recap_rss_rssfeeddata" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on rssfeedstatus
--
ALTER TABLE "recap_rss_rssfeedstatus" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:06:39.638396+00:00'::timestamptz;
ALTER TABLE "recap_rss_rssfeedstatus" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on rssfeedstatus
--
ALTER TABLE "recap_rss_rssfeedstatus" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:06:39.661652+00:00'::timestamptz;
ALTER TABLE "recap_rss_rssfeedstatus" ALTER COLUMN "date_modified" DROP DEFAULT;
COMMIT;
