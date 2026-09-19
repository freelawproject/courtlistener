--
-- Concurrently create index recap_pacerhtmlfiles_ct_obj_idx on field(s) content_type, object_id of model pacerhtmlfiles
--
CREATE INDEX CONCURRENTLY "recap_pacerhtmlfiles_ct_obj_idx" ON "recap_pacerhtmlfiles" ("content_type_id", "object_id");
