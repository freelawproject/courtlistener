--
-- Add field html_anon_2020 to opinion
--
-- Note that this is not done in a transaction b/c you can't alter data and
-- schemas in the same transaction.
ALTER TABLE "search_opinion" ADD COLUMN "html_anon_2020" text;
UPDATE "search_opinion" set "html_anon_2020" = '' WHERE "html_anon_2020" IS NULL;
ALTER TABLE "search_opinion" ALTER COLUMN "html_anon_2020" SET NOT NULL;

