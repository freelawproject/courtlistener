import sentry_sdk
from asgiref.sync import async_to_sync

from cl.lib.sentry import set_scraper_tags
from cl.tests.cases import SimpleTestCase


class ScraperTagsTest(SimpleTestCase):
    def test_tags_reach_code_run_through_async_to_sync(self) -> None:
        """The tags set before async_to_sync must reach the worker thread."""

        async def read_tags() -> dict[str, str]:
            return dict(sentry_sdk.get_isolation_scope()._tags)

        # the forked scope must not change the process-wide scope
        before = dict(sentry_sdk.get_isolation_scope()._tags)
        with sentry_sdk.isolation_scope():
            set_scraper_tags("ky", "opinions")
            tags = async_to_sync(read_tags)()

        self.assertEqual(tags["court_id"], "ky")
        self.assertEqual(tags["scrape_kind"], "opinions")
        self.assertEqual(tags["owner"], "juriscraper")
        self.assertEqual(dict(sentry_sdk.get_isolation_scope()._tags), before)
