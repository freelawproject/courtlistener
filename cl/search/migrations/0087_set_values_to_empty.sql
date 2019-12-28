BEGIN;
--
-- Raw SQL operation
--
UPDATE "search_opinion" SET "html" = '' WHERE "html" IS NULL;
--
-- Raw SQL operation
--
UPDATE "search_opinion" SET "html_columbia" = '' WHERE "html_columbia" IS NULL;
--
-- Raw SQL operation
--
UPDATE "search_opinion" SET "html_lawbox" = '' WHERE "html_lawbox" IS NULL;
COMMIT;
