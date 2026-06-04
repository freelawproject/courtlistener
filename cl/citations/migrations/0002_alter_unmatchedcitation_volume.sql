--
-- Custom state/database change combination
--
DROP INDEX CONCURRENTLY IF EXISTS citations_u_volume_da4d25_idx;

ALTER TABLE citations_unmatchedcitation
DROP CONSTRAINT IF EXISTS citations_unmatchedcitat_citing_opinion_id_volume_ca9f46d3_uniq;

ALTER TABLE citations_unmatchedcitation ALTER COLUMN volume TYPE text USING volume::text;

CREATE UNIQUE INDEX CONCURRENTLY citations_unmatchedcitation_citing_opinion_id_volume_uniq_idx
ON citations_unmatchedcitation (citing_opinion_id, volume, reporter, page);

ALTER TABLE citations_unmatchedcitation
ADD CONSTRAINT citations_unmatchedcitat_citing_opinion_id_volume_ca9f46d3_uniq
UNIQUE USING INDEX citations_unmatchedcitation_citing_opinion_id_volume_uniq_idx;

CREATE INDEX CONCURRENTLY citations_u_volume_da4d25_idx
ON citations_unmatchedcitation (volume, reporter, page);
