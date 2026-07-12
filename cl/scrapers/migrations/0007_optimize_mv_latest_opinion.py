from django.db import migrations

NEW_MV_SQL = """
CREATE MATERIALIZED VIEW scrapers_mv_latest_opinion AS
(
    WITH scraper_courts AS (
        SELECT id AS court_id
        FROM search_court
        WHERE has_opinion_scraper
    ),
    recent_courts AS (
        /*
            Courts with any cluster activity in the staleness window.
            Uses the search_opinioncluster.date_created btree index, so
            this slice is cheap regardless of total table size.
        */
        SELECT DISTINCT sd.court_id
        FROM search_opinioncluster soc
        INNER JOIN search_docket sd ON sd.id = soc.docket_id
        WHERE soc.date_created > now() - interval '7 days'
          AND sd.court_id IN (SELECT court_id FROM scraper_courts)
    ),
    stale_courts AS (
        SELECT court_id FROM scraper_courts
        EXCEPT
        SELECT court_id FROM recent_courts
    )
    /*
        For each stale court, aggregate the latest cluster date.
        cluster.date_created is used as a proxy for opinion.date_created:
        scrapers create cluster + opinion in the same transaction, so the
        two timestamps track each other. This avoids touching the much
        larger search_opinion table.
    */
    SELECT
        sd.court_id,
        max(soc.date_created) AS latest_creation_date,
        DATE_TRUNC('minutes', (now() - max(soc.date_created)))::text AS time_since,
        now() AS view_last_updated
    FROM stale_courts sc
    INNER JOIN search_docket sd ON sd.court_id = sc.court_id
    INNER JOIN search_opinioncluster soc ON soc.docket_id = sd.id
    GROUP BY sd.court_id
    ORDER BY 2 DESC
)
WITH NO DATA;
"""

ORIGINAL_MV_SQL = """
CREATE MATERIALIZED VIEW scrapers_mv_latest_opinion AS
(
    SELECT
        court_id,
        max(so.date_created) as latest_creation_date,
        DATE_TRUNC('minutes', (now() - max(so.date_created)))::text as time_since,
        now() as view_last_updated
    FROM
        (
            SELECT id, court_id
            FROM search_docket
            WHERE court_id IN (
                SELECT id
                FROM search_court
                WHERE
                    has_opinion_scraper
                    AND in_use
            )
        ) sd
    INNER JOIN
        (SELECT id, docket_id FROM search_opinioncluster) soc ON soc.docket_id = sd.id
    INNER JOIN
        search_opinion so ON so.cluster_id = soc.id
    GROUP BY
        sd.court_id
    HAVING
        now() - max(so.date_created) > interval '7 days'
    ORDER BY
        2 DESC
)
WITH NO DATA;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0006_accountsubscription"),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"DROP MATERIALIZED VIEW IF EXISTS scrapers_mv_latest_opinion;\n{NEW_MV_SQL}",
            reverse_sql=f"DROP MATERIALIZED VIEW IF EXISTS scrapers_mv_latest_opinion;\n{ORIGINAL_MV_SQL}",
        ),
    ]
