import os
import shutil
import tempfile
from unittest import mock

from django.conf import settings
from django.core.management import call_command

from cl.lib.redis_utils import get_redis_interface
from cl.search.factories import CourtFactory
from cl.search.models import Docket
from cl.tests.cases import TestCase


# Use a cache-key prefix distinct from the other RSS tests so the shared Redis
# cache can't collide across parallel test workers.
@mock.patch(
    "cl.recap_rss.tasks.rss_cache_prefix",
    return_value="rss_hash_test_import",
)
@mock.patch("cl.recap_rss.tasks.enqueue_docket_alert")
class ImportRssArchiveTest(TestCase):
    """Can we ingest a donated archive of historical RSS feed files?"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="ca10", jurisdiction="F")

    @classmethod
    def clean_rss_redis_cache(cls) -> None:
        r = get_redis_interface("CACHE")
        keys = r.keys("rss_hash_test_import:*")
        if keys:
            r.delete(*keys)

    def setUp(self) -> None:
        # Lay out a tiny archive, <root>/<court_id>/<court_id>-<epoch_ms>.rss,
        # from the same sample feed the recap_rss ingestion tests use.
        sample = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", "rss_ca10.xml"
        )
        self.root = tempfile.mkdtemp()
        court_dir = os.path.join(self.root, "ca10")
        os.mkdir(court_dir)
        shutil.copyfile(
            sample, os.path.join(court_dir, "ca10-1448181012075.rss")
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root)
        # The item-hash cache lives in Redis, so it isn't rolled back with the
        # test transaction; clear it between tests.
        self.clean_rss_redis_cache()

    def test_ingests_feed_files(self, mock_enqueue, mock_cache_prefix) -> None:
        """Does each feed file get merged into dockets and entries?"""
        call_command("import_rss_archive", root=self.root, courts=["ca10"])
        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 3)
        for docket in dockets:
            self.assertEqual(docket.docket_entries.count(), 1)

    def test_reingest_creates_no_duplicates(
        self, mock_enqueue, mock_cache_prefix
    ) -> None:
        """Does re-running over the same archive avoid duplicates, even once
        the item-hash cache has expired?
        """
        call_command("import_rss_archive", root=self.root, courts=["ca10"])
        # Clear the cache so the second pass relies on the durable
        # (docket, entry_number) dedup rather than the item-hash cache.
        self.clean_rss_redis_cache()
        call_command("import_rss_archive", root=self.root, courts=["ca10"])
        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 3)
        for docket in dockets:
            self.assertEqual(docket.docket_entries.count(), 1)

    def test_skips_unknown_court_directory(
        self, mock_enqueue, mock_cache_prefix
    ) -> None:
        """Do we skip directories that don't name a known PACER court?"""
        os.mkdir(os.path.join(self.root, "not-a-court"))
        call_command("import_rss_archive", root=self.root)
        # The ca10 feed still merges; the unknown directory is ignored.
        self.assertEqual(Docket.objects.count(), 3)

    def test_skips_malformed_feed_file(
        self, mock_enqueue, mock_cache_prefix
    ) -> None:
        """Is an unparseable feed file skipped without aborting the run?"""
        # Drop an undecodable file beside the good ca10 sample.
        with open(
            os.path.join(self.root, "ca10", "ca10-1448181099999.rss"), "wb"
        ) as f:
            f.write(b"\xff\xfe not valid utf-8 \xff")
        call_command("import_rss_archive", root=self.root, courts=["ca10"])
        # The good feed still merges its 3 dockets; the bad file is skipped.
        self.assertEqual(Docket.objects.count(), 3)

    def test_skips_empty_feed_file(
        self, mock_enqueue, mock_cache_prefix
    ) -> None:
        """Does a feed with no items produce no dockets (and no error)?"""
        court_dir = os.path.join(self.root, "ca10")
        for name in os.listdir(court_dir):
            os.remove(os.path.join(court_dir, name))
        empty_feed = (
            '<?xml version="1.0" encoding="ISO-8859-1"?>'
            '<rss version="2.0"><channel>'
            "<title>Tenth Circuit</title>"
            "<link>https://ecf.ca10.uscourts.gov</link>"
            "<description>Docket entries of type: opinions</description>"
            "</channel></rss>"
        )
        with open(os.path.join(court_dir, "ca10-1448181099999.rss"), "w") as f:
            f.write(empty_feed)
        call_command("import_rss_archive", root=self.root, courts=["ca10"])
        self.assertEqual(Docket.objects.count(), 0)

    def test_pacer_court_dir_maps_to_cl_court(
        self, mock_enqueue, mock_cache_prefix
    ) -> None:
        """Is a PACER-coded directory ingested under its CourtListener court?"""
        # 'azb' is the PACER code for CL's 'arb' (Arizona Bankruptcy Court).
        CourtFactory(id="arb", jurisdiction="FB")
        sample = os.path.join(
            settings.INSTALL_ROOT,
            "cl",
            "recap",
            "test_assets",
            "rss_sample_unnumbered_mdb.xml",
        )
        azb_dir = os.path.join(self.root, "azb")
        os.mkdir(azb_dir)
        shutil.copyfile(sample, os.path.join(azb_dir, "azb-1448181012075.rss"))
        call_command("import_rss_archive", root=self.root, courts=["arb"])
        self.assertEqual(Docket.objects.filter(court_id="arb").count(), 1)
