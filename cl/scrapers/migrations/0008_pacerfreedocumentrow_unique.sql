--
-- Custom state/database change combination
--
-- PERF: Built CONCURRENTLY so no ACCESS EXCLUSIVE lock is taken on the large
-- scrapers_pacerfreedocumentrow table. CONCURRENTLY cannot run inside a
-- transaction block, so there is intentionally no BEGIN/COMMIT wrapper.
CREATE UNIQUE INDEX CONCURRENTLY "scrapers_pfdr_court_doc_uniq" ON "scrapers_pacerfreedocumentrow" ("court_id", "pacer_doc_id") WHERE "pacer_doc_id" <> '';
