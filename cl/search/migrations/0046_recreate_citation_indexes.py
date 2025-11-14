from django.db import migrations, models
from django.contrib.postgres.operations import AddIndexConcurrently

class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('search', '0045_alter_volume_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Recreate unique index and constraint
                migrations.RunSQL(
                    sql="""
                        CREATE UNIQUE INDEX CONCURRENTLY search_citation_cluster_id_uniq_idx
                        ON search_citation (cluster_id, volume, reporter, page);
                        """,
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS search_citation_cluster_id_uniq_idx;",
                ),
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE search_citation
                        ADD CONSTRAINT search_citation_cluster_id_7a668830aad411f5_uniq
                        UNIQUE USING INDEX search_citation_cluster_id_uniq_idx;
                        """,
                    reverse_sql=migrations.RunSQL.noop,
                ),

                # Regular concurrent indexes
                AddIndexConcurrently(
                    model_name='citation',
                    index=models.Index(
                        fields=['volume', 'reporter', 'page'],
                        name='search_citation_volume_ae340b5b02e8912_idx',
                    ),
                ),
                AddIndexConcurrently(
                    model_name='citation',
                    index=models.Index(
                        fields=['volume', 'reporter'],
                        name='search_citation_volume_251bc1d270a8abee_idx',
                    ),
                ),
            ],
            state_operations=[],
        ),
    ]
