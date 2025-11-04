from django.core.management import call_command

from cl.lib.redis_utils import get_redis_interface
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket
from cl.tests.cases import TestCase


class CleanDocketNumberRawCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court_canb = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_ca1 = CourtFactory(id="ca1", jurisdiction="F")
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket_1 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="12-1234-ag",
            docket_number="docket_number",
            source=Docket.DEFAULT,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court_ca1,
            docket_number_raw="Docket 1567",
            docket_number="docket_number",
            source=Docket.DEFAULT,
        )
        cls.docket_3 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket Nos. 12-1234-ag, 1235",
            docket_number="docket_number",
            source=Docket.DEFAULT,
        )
        cls.docket_4 = DocketFactory(
            court=cls.court_ca1,
            docket_number_raw="Docket 1567",
            docket_number="docket_number",
            source=Docket.RECAP,
        )
        cls.docket_5 = DocketFactory(
            court=cls.court_canb,
            docket_number_raw="12-1234",
            docket_number="docket_number",
            source=Docket.DEFAULT,
        )
        cls.expected_docket_numbers = [
            "12-1234-AG",
            "1567",
            "docket_number",  # Dockets without generic format should be sent to LLM cleaning
            "docket_number",  # Dockets from recap source shouldn't be changed
            "docket_number",  # Dockets from non-F courts shouldn't be changed
        ]

    def setUp(self) -> None:
        self.r = get_redis_interface("CACHE")
        key_to_clean = "docket_number_cleaning:llm_batch"
        key = self.r.keys(key_to_clean)
        if key:
            self.r.delete(*key)

    def test_docket_number_cleaning(self):
        call_command(
            "clean_docket_number_raw", court_ids=["scotus", "ca1", "canb"]
        )

        for i, docket in enumerate(
            [
                self.docket_1,
                self.docket_2,
                self.docket_3,
                self.docket_4,
                self.docket_5,
            ]
        ):
            docket.refresh_from_db()
            self.assertEqual(
                docket.docket_number,
                self.expected_docket_numbers[i],
                f"Docket number doesn't match for docket id {docket.id}",
            )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            1,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set([str(self.docket_3.id)]),
            "Redis cache set doesn't match",
        )
