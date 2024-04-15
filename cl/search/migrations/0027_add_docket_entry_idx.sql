--
-- Concurrently create index entry_number_idx on field(s) entry_number,
-- docket_id of model docketentry
--
CREATE INDEX CONCURRENTLY "entry_number_idx" ON "search_docketentry" (
  "docket_id",
  "entry_number"
) WHERE "entry_number" = 1;
