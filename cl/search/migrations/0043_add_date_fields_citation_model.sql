BEGIN;
--
-- Add field date_created to citation
--
ALTER TABLE "search_citation" ADD COLUMN "date_created" timestamp with time zone DEFAULT '2025-09-25 17:01:18.388479+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citation" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Add field date_modified to citation
--
ALTER TABLE "search_citation" ADD COLUMN "date_modified" timestamp with time zone DEFAULT '2025-09-25 17:01:18.422450+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citation" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Add field date_created to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "date_created" timestamp with time zone DEFAULT '2025-09-25 17:01:18.506535+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citationevent" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Add field date_modified to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "date_modified" timestamp with time zone DEFAULT '2025-09-25 17:01:18.593022+00:00'::timestamptz NOT NULL;
ALTER TABLE "search_citationevent" ALTER COLUMN "date_modified" DROP DEFAULT;

CREATE INDEX "search_citation_date_created_76e2f9fd" ON "search_citation" ("date_created");
CREATE INDEX "search_citation_date_modified_37809628" ON "search_citation" ("date_modified");
COMMIT;