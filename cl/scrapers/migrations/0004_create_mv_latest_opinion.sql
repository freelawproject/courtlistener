BEGIN;
--
-- Create model MVLatestOpinion
--
-- (no-op)
--
-- Raw SQL operation
--

        CREATE MATERIALIZED VIEW IF NOT EXISTS
            scrapers_mv_latest_opinion
        AS
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
                    /*
                        Only check courts with scrapers in use
                    */
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
            /*
                Only return results for courts with no updates in a week
            */
            now() - max(so.date_created) > interval '7 days'
        ORDER BY
            2 DESC
        )
        ;
COMMIT;
