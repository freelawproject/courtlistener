import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations, models

BATCH_SIZE = 200_000

DO_BATCH_SQL = f"""
DO $$
DECLARE
    batch_size integer := {BATCH_SIZE};
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
"""

class Migration(migrations.Migration):

    dependencies = [
        ('search', '0044_remove_citation_indexes'),
    ]

    operations = [
        # Remove triggers first so they won't block DROP COLUMN
        pgtrigger.migrations.RemoveTrigger(
            model_name='citation',
            name='update_update',
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name='citation',
            name='delete_delete',
        ),

        # Separate database operations and model state
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # create the temporary column
                migrations.RunSQL(
                    sql='ALTER TABLE search_citation ADD COLUMN volume_new text;',
                    reverse_sql='ALTER TABLE search_citation DROP COLUMN IF EXISTS volume_new;',
                ),

                # batch copy values using a DO $$ pgSQL block
                migrations.RunSQL(sql=DO_BATCH_SQL, reverse_sql=migrations.RunSQL.noop),

                # drop old column and rename new column, do this inside the same transaction
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE search_citation DROP COLUMN volume;
                        ALTER TABLE search_citation RENAME COLUMN volume_new TO volume;
                    """,
                    reverse_sql="""
                        ALTER TABLE search_citation ADD COLUMN volume_new integer;
                        UPDATE search_citation SET volume_new = volume::integer;
                        ALTER TABLE search_citation DROP COLUMN volume;
                        ALTER TABLE search_citation RENAME COLUMN volume_new TO volume;
                        """,
                ),

                # alter citationevent.volume type to text
                migrations.RunSQL(
                    sql='ALTER TABLE search_citationevent ALTER COLUMN volume TYPE text USING volume::text;',
                    reverse_sql='ALTER TABLE search_citationevent ALTER COLUMN volume TYPE integer USING volume::integer;',
                ),
            ],
            state_operations=[
                # tell Django model state the field is now TextField
                migrations.AlterField(
                    model_name='citation',
                    name='volume',
                    field=models.TextField(help_text='The volume of the reporter'),
                ),
                migrations.AlterField(
                    model_name='citationevent',
                    name='volume',
                    field=models.TextField(help_text='The volume of the reporter'),
                ),
            ],
        ),

        # Readd triggers after changes
        pgtrigger.migrations.AddTrigger(
            model_name='citation',
            trigger=pgtrigger.compiler.Trigger(
                name='update_update',
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition=(
                        'WHEN (OLD."cluster_id" IS DISTINCT FROM (NEW."cluster_id") OR '
                        'OLD."id" IS DISTINCT FROM (NEW."id") OR '
                        'OLD."page" IS DISTINCT FROM (NEW."page") OR '
                        'OLD."reporter" IS DISTINCT FROM (NEW."reporter") OR '
                        'OLD."type" IS DISTINCT FROM (NEW."type") OR '
                        'OLD."volume" IS DISTINCT FROM (NEW."volume"))'
                    ),
                    func=(
                        'INSERT INTO "search_citationevent" '
                        '("cluster_id","date_created","date_modified","id","page","pgh_context_id","pgh_created_at","pgh_label","pgh_obj_id","reporter","type","volume") '
                        'VALUES (OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."id", OLD."page", _pgh_attach_context(), NOW(), \'update\', OLD."id", OLD."reporter", OLD."type", OLD."volume"); RETURN NULL;'
                    ),
                    hash='67f49dac0438e0bbed0fe935c7135731cb6d0f2d',
                    operation='UPDATE',
                    pgid='pgtrigger_update_update_8c292',
                    table='search_citation',
                    when='AFTER',
                )
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name='citation',
            trigger=pgtrigger.compiler.Trigger(
                name='delete_delete',
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func=(
                        'INSERT INTO "search_citationevent" '
                        '("cluster_id","date_created","date_modified","id","page","pgh_context_id","pgh_created_at","pgh_label","pgh_obj_id","reporter","type","volume") '
                        'VALUES (OLD."cluster_id", OLD."date_created", OLD."date_modified", OLD."id", OLD."page", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."reporter", OLD."type", OLD."volume"); RETURN NULL;'
                    ),
                    hash='1b1d26be5f3161f19fbd77bb5782c733e5015fc9',
                    operation='DELETE',
                    pgid='pgtrigger_delete_delete_58ea6',
                    table='search_citation',
                    when='AFTER',
                )
            ),
        ),
    ]
