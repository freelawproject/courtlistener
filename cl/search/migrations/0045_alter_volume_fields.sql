BEGIN;
--
-- Custom state/database change combination
--
ALTER TABLE search_citation ADD COLUMN volume_new text;

DO $$
DECLARE
    batch_size integer := 200000;
    min_id bigint;
    max_id bigint;
    current_id bigint;
BEGIN
    SELECT MIN(id), MAX(id) INTO min_id, max_id FROM search_citation;
    IF min_id IS NULL THEN
        RETURN;
    END IF;

    current_id := min_id;
    WHILE current_id <= max_id LOOP
        UPDATE search_citation
        SET volume_new = volume::text
        WHERE id >= current_id AND id < current_id + batch_size;

        RAISE NOTICE 'Updated rows with id % to %', current_id, current_id + batch_size - 1;

        current_id := current_id + batch_size;
    END LOOP;
END
$$;


ALTER TABLE search_citation DROP COLUMN volume;
ALTER TABLE search_citation RENAME COLUMN volume_new TO volume;

COMMIT;

BEGIN;

ALTER TABLE search_citationevent ALTER COLUMN volume TYPE text USING volume::text;

COMMIT;
