--
-- Concurrently create index search_dock_court_i_a043ae_idx on field(s) court_id, id of model docket
--
CREATE INDEX CONCURRENTLY "search_dock_court_i_a043ae_idx" ON "search_docket" ("court_id", "id");
