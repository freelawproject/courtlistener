--
-- Concurrently create index district_court_docket_lookup_idx on field(s) court_id, docket_number_core, pacer_case_id of model docket
--
CREATE INDEX CONCURRENTLY "district_court_docket_lookup_idx" ON "search_docket" ("court_id", "docket_number_core", "pacer_case_id");
