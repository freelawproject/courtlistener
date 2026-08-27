BEGIN;
--
-- Raw SQL operation
--
DROP MATERIALIZED VIEW IF EXISTS scrapers_mv_latest_opinion;

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

COMMIT;
