--
-- Concurrently create index alerts_sche_content_c5e627_idx on field(s) content_type, object_id of model scheduledalerthit
--
CREATE INDEX CONCURRENTLY "alerts_sche_content_c5e627_idx" ON "alerts_scheduledalerthit" ("content_type_id", "object_id");
