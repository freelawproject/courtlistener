--
-- Raw SQL operation
--
DROP INDEX CONCURRENTLY IF EXISTS search_citation_volume_ae340b5b02e8912_idx;
--
-- Raw SQL operation
--
DROP INDEX CONCURRENTLY IF EXISTS search_citation_volume_251bc1d270a8abee_idx;
--
-- Raw SQL operation
--
ALTER TABLE search_citation DROP CONSTRAINT IF EXISTS search_citation_cluster_id_7a668830aad411f5_uniq;
--
-- Alter field volume on citation
--
ALTER TABLE "search_citation" ALTER COLUMN "volume" TYPE text USING "volume"::text;
--
-- Raw SQL operation
--

                    ALTER TABLE search_citation ADD CONSTRAINT search_citation_cluster_id_7a668830aad411f5_uniq
                        UNIQUE (cluster_id, volume, reporter, page);
                    
--
-- Raw SQL operation
--

                    CREATE INDEX CONCURRENTLY search_citation_volume_ae340b5b02e8912_idx
                        ON search_citation (volume, reporter, page);
                    
--
-- Raw SQL operation
--

                    CREATE INDEX CONCURRENTLY search_citation_volume_251bc1d270a8abee_idx
                        ON search_citation (volume, reporter);