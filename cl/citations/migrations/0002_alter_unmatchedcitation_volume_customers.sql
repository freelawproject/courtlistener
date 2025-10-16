--
-- Raw SQL operation
--
DROP INDEX CONCURRENTLY IF EXISTS citations_u_volume_da4d25_idx;
--
-- Raw SQL operation
--

                ALTER TABLE citations_unmatchedcitation
                DROP CONSTRAINT IF EXISTS citations_unmatchedcitat_citing_opinion_id_volume_ca9f46d3_uniq;

--
-- Alter field volume on unmatchedcitation
--
ALTER TABLE "citations_unmatchedcitation" ALTER COLUMN "volume" TYPE text USING "volume"::text;
--
-- Raw SQL operation
--

                ALTER TABLE citations_unmatchedcitation
                    ADD CONSTRAINT citations_unmatchedcitat_citing_opinion_id_volume_ca9f46d3_uniq
                    UNIQUE (citing_opinion_id, volume, reporter, page);

--
-- Raw SQL operation
--

                CREATE INDEX CONCURRENTLY citations_u_volume_da4d25_idx
                    ON citations_unmatchedcitation (volume, reporter, page);
