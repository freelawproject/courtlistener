--
-- Concurrently create index pacer_doc_id_idx on field(s) pacer_doc_id of model recapdocument
--

CREATE INDEX CONCURRENTLY "pacer_doc_id_idx" ON "search_recapdocument" ("pacer_doc_id") WHERE NOT ("pacer_doc_id" = '');
