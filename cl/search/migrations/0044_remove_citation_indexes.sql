--
-- Custom state/database change combination
--
DROP INDEX CONCURRENTLY IF EXISTS "search_citation_volume_ae340b5b02e8912_idx";
DROP INDEX CONCURRENTLY IF EXISTS "search_citation_volume_251bc1d270a8abee_idx";
ALTER TABLE search_citation DROP CONSTRAINT IF EXISTS search_citation_cluster_id_7a668830aad411f5_uniq;