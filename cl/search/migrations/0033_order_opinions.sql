BEGIN;
--
-- Add field ordering_key to opinion
--
ALTER TABLE "search_opinion" ADD COLUMN "ordering_key" integer NULL;
--
-- Add field ordering_key to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "ordering_key" integer NULL;
--
-- Create constraint unique_opinion_ordering_key on model opinion
--
ALTER TABLE "search_opinion" ADD CONSTRAINT "unique_opinion_ordering_key" UNIQUE ("cluster_id", "ordering_key");
COMMIT;
