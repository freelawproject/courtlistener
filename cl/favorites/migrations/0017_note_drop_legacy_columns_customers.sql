--
-- Drop the legacy per-type FK columns (also drops their FK, index and
-- unique_together constraints)
--
ALTER TABLE "favorites_note" DROP COLUMN "audio_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "cluster_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "docket_id_id";
ALTER TABLE "favorites_note" DROP COLUMN "recap_doc_id_id";
