"""Sentry helpers for scraper work."""

import sentry_sdk


def set_scraper_tags(
    court_id: str | None, kind: str, owner: str = "juriscraper"
) -> None:
    """Tag every event captured in the current isolation scope.

    Celery opens one scope per task and the scrape commands one per court.

    :param court_id: the CourtListener court pk, if known
    :param kind: "opinions", "oral_args", "backscrape", "extract-from-text",
        "email", "pacer" or "state-docket"
    :param owner: who should look at events from this work
    """
    scope = sentry_sdk.get_isolation_scope()
    scope.set_tag("scrape_kind", kind)
    scope.set_tag("owner", owner)
    if court_id:
        scope.set_tag("court_id", court_id)
