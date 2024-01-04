--
-- Create constraint unique_docket_per_court on model docket
--
CREATE UNIQUE INDEX CONCURRENTLY "unique_docket_per_court" ON "search_docket" ((MD5("docket_number")), "pacer_case_id", "court_id");
--
-- Concurrently create index hash_docket_number_lookup_idx on field(s)  of model docket
--
CREATE INDEX CONCURRENTLY "hash_docket_number_lookup_idx" ON "search_docket" ((MD5("docket_number")));

