from django.db import migrations
from django.contrib.postgres.operations import RemoveIndexConcurrently

class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('search', '0043_add_date_fields_citation_model'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                RemoveIndexConcurrently(
                    model_name='citation',
                    name='search_citation_volume_ae340b5b02e8912_idx',
                ),
                RemoveIndexConcurrently(
                    model_name='citation',
                    name='search_citation_volume_251bc1d270a8abee_idx',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE search_citation DROP CONSTRAINT IF EXISTS search_citation_cluster_id_7a668830aad411f5_uniq;',
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],  # no model state changes
        ),
    ]