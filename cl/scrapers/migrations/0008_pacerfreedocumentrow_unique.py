from django.db import migrations, models


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    atomic = False

    dependencies = [
        ("scrapers", "0007_optimize_mv_latest_opinion"),
    ]

    operations = [
        # Build the unique index CONCURRENTLY so we don't take an
        # ACCESS EXCLUSIVE lock on this large table. SeparateDatabaseAndState
        # lets Django's migration state record a UniqueConstraint (matching the
        # model's Meta) while the database gets the concurrently-built index.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'CREATE UNIQUE INDEX CONCURRENTLY "scrapers_pfdr_court_doc_uniq" '
                        'ON "scrapers_pacerfreedocumentrow" ("court_id", "pacer_doc_id") '
                        "WHERE \"pacer_doc_id\" <> '';"
                    ),
                    reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS "scrapers_pfdr_court_doc_uniq";',
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="pacerfreedocumentrow",
                    constraint=models.UniqueConstraint(
                        fields=["court_id", "pacer_doc_id"],
                        condition=models.Q(("pacer_doc_id", ""), _negated=True),
                        name="scrapers_pfdr_court_doc_uniq",
                    ),
                ),
            ],
        ),
    ]
