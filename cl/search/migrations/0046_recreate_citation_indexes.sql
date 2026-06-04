--
-- Custom state/database change combination
--

CREATE UNIQUE INDEX CONCURRENTLY search_citation_cluster_id_uniq_idx
ON search_citation (cluster_id, volume, reporter, page);

ALTER TABLE search_citation
ADD CONSTRAINT search_citation_cluster_id_7a668830aad411f5_uniq
UNIQUE USING INDEX search_citation_cluster_id_uniq_idx;

CREATE INDEX CONCURRENTLY "search_citation_volume_ae340b5b02e8912_idx" ON "search_citation" ("volume", "reporter", "page");
CREATE INDEX CONCURRENTLY "search_citation_volume_251bc1d270a8abee_idx" ON "search_citation" ("volume", "reporter");
