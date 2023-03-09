BEGIN;
--
-- Rename model Favorite to Note
--
ALTER TABLE "favorites_favorite" RENAME TO "favorites_note";
COMMIT;
