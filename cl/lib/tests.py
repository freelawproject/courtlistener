import datetime
import pickle
from typing import TypedDict, cast
from unittest import mock
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils.functional import SimpleLazyObject
from requests.cookies import RequestsCookieJar

from cl.lib.courts import (
    get_active_court_from_cache,
    get_minimal_list_of_courts,
    lookup_child_courts_cache,
)
from cl.lib.date_time import midnight_pt
from cl.lib.decorators import _memory_cache, clear_tiered_cache, tiered_cache
from cl.lib.elasticsearch_utils import append_query_conjunctions
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.mime_types import lookup_mime_type
from cl.lib.model_helpers import (
    clean_docket_number,
    is_docket_number,
    linkify_orig_docket_number,
    make_docket_number_core,
    make_scotus_docket_number_core,
    make_upload_path,
)
from cl.lib.pacer import (
    get_blocked_status,
    make_address_lookup_key,
    normalize_attorney_contact,
    normalize_attorney_role,
    normalize_us_state,
)
from cl.lib.pacer_session import (
    ProxyPacerSession,
    SessionData,
    get_or_cache_pacer_cookies,
    session_key,
)
from cl.lib.privacy_tools import anonymize
from cl.lib.ratelimiter import parse_rate
from cl.lib.recap_utils import needs_ocr
from cl.lib.redis_utils import (
    acquire_redis_lock,
    get_redis_interface,
    release_redis_lock,
)
from cl.lib.s3_cache import get_s3_cache, make_s3_cache_key
from cl.lib.search_index_utils import get_parties_from_case_name_bankr
from cl.lib.sqlcommenter import QueryWrapper, SqlCommenter, add_sql_comment
from cl.lib.string_utils import normalize_dashes, trunc
from cl.lib.utils import (
    check_for_proximity_tokens,
    check_unbalanced_parenthesis,
    check_unbalanced_quotes,
    sanitize_unbalanced_parenthesis,
    sanitize_unbalanced_quotes,
)
from cl.people_db.models import Role
from cl.recap.models import UPLOAD_TYPE, PacerHtmlFiles
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterWithMultipleOpinionsFactory,
)
from cl.search.models import Court, Docket, Opinion, OpinionCluster
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class TestPacerUtils(TestCase):
    fixtures = ["court_data.json"]

    def test_auto_blocking_small_bankr_docket(self) -> None:
        """Do we properly set small bankruptcy dockets to private?"""
        d = Docket()
        d.court = Court.objects.get(pk="akb")
        blocked, date_blocked = async_to_sync(get_blocked_status)(d)
        self.assertTrue(
            blocked,
            msg="Bankruptcy dockets with few entries should be blocked.",
        )
        blocked, date_blocked = async_to_sync(get_blocked_status)(
            d, count_override=501
        )
        self.assertFalse(
            blocked,
            msg="Bankruptcy dockets with many entries should not be blocked",
        )
        # This should stay blocked even though it's a big bankruptcy docket.
        d.blocked = True
        blocked, date_blocked = async_to_sync(get_blocked_status)(
            d, count_override=501
        )
        self.assertTrue(
            blocked,
            msg="Bankruptcy dockets that start blocked should stay blocked.",
        )


@mock.patch(
    "cl.lib.courts.get_cache_key_for_court_list",
    return_value="lib_test:minimal-court-list",
)
class TestCachedCourtUtils(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent_court = CourtFactory(id="parent_court")
        cls.child_court_1 = CourtFactory(
            id="child_1", jurisdiction="FB", parent_court=cls.parent_court
        )
        cls.child_court_2 = CourtFactory(
            id="child_2",
            jurisdiction="FB",
            parent_court=cls.parent_court,
        )
        cls.court_not_in_use = CourtFactory(in_use=False)

        cls.self_referencing_court = CourtFactory(
            id="self_ref", parent_court_id="self_ref"
        )
        cls.self_referencing_child_1 = CourtFactory(
            parent_court=cls.self_referencing_court
        )
        cls.self_referencing_child_1_1 = CourtFactory(
            parent_court=cls.self_referencing_court
        )
        cls.self_referencing_child_2 = CourtFactory(
            parent_court=cls.self_referencing_court
        )

    def setUp(self):
        # Pre-populate the cache with the court list
        with patch(
            "cl.lib.courts.get_cache_key_for_court_list",
            return_value="lib_test:minimal-court-list",
        ):
            get_minimal_list_of_courts()

    def test_can_get_active_courts_from_cache(self, mock_cache_key):
        with self.assertNumQueries(0):
            in_use_courts = get_active_court_from_cache()

        court_count = Court.objects.filter(in_use=True).count()
        self.assertEqual(len(in_use_courts), court_count)

    def test_can_handle_empty_inputs(self, mock_cache_key):
        with self.assertNumQueries(0):
            child_ids = lookup_child_courts_cache([])

        self.assertEqual(child_ids, set())

    def test_can_return_empty_set_for_court_w_no_child(self, mock_cache_key):
        with self.assertNumQueries(0):
            child_ids = lookup_child_courts_cache([self.court_not_in_use.pk])

        self.assertEqual(child_ids, set())

    def test_can_return_set_with_child_court_ids(self, mock_cache_key):
        with self.assertNumQueries(0):
            child_ids = lookup_child_courts_cache([self.parent_court.pk])

        self.assertSetEqual(
            {
                self.parent_court.pk,
                self.child_court_1.pk,
                self.child_court_2.pk,
            },
            child_ids,
        )

    def test_can_handle_self_referencing_courts(self, mock_cache_key):
        with self.assertNumQueries(0):
            child_ids = lookup_child_courts_cache(
                [self.self_referencing_court.pk]
            )

        self.assertSetEqual(
            {
                self.self_referencing_court.pk,
                self.self_referencing_child_1.pk,
                self.self_referencing_child_1_1.pk,
                self.self_referencing_child_2.pk,
            },
            child_ids,
        )

    def tearDown(self):
        cache.delete("lib_test:minimal-court-list")
        return super().tearDown()


@override_settings(
    EGRESS_PROXY_HOSTS=["http://proxy_1:9090", "http://proxy_2:9090"]
)
class TestPacerSessionUtils(TestCase):
    def setUp(self) -> None:
        r = get_redis_interface("CACHE", decode_responses=False)
        # Clear cached session keys to prevent data inconsistencies.
        key = r.keys(session_key % "test_user_new_cookie")
        if key:
            r.delete(*key)
        self.test_cookies = RequestsCookieJar()
        self.test_cookies.set("PacerSession", "this-is-a-test")
        r.set(
            session_key % "test_user_new_format",
            pickle.dumps(
                SessionData(self.test_cookies, "http://proxy_1:9090")
            ),
            ex=60 * 60,
        )
        r.set(
            session_key % "test_new_format_almost_expired",
            pickle.dumps(
                SessionData(self.test_cookies, "http://proxy_1:9090")
            ),
            ex=60,
        )

    def test_pick_random_proxy_when_list_is_available(self):
        """Does ProxyPacerSession choose a random proxy from the available list?"""
        session = ProxyPacerSession(username="test", password="password")
        self.assertIn(
            session.proxy_address,
            ["http://proxy_1:9090", "http://proxy_2:9090"],
        )

    @patch("cl.lib.pacer_session.log_into_pacer")
    def test_compute_new_cookies_with_new_format(self, mock_log_into_pacer):
        """Are we using the dataclass for new cookies?"""
        mock_log_into_pacer.return_value = SessionData(
            self.test_cookies,
            "http://proxy_1:9090",
        )
        session_data = async_to_sync(get_or_cache_pacer_cookies)(
            "test_user_new_cookie", username="test", password="password"
        )
        self.assertEqual(mock_log_into_pacer.call_count, 1)
        self.assertIsInstance(session_data, SessionData)
        self.assertEqual(session_data.proxy_address, "http://proxy_1:9090")

    @patch("cl.lib.pacer_session.log_into_pacer")
    def test_parse_cookie_proxy_pair_properly(self, mock_log_into_pacer):
        """Can we parse the dataclass from cache properly?"""
        session_data = async_to_sync(get_or_cache_pacer_cookies)(
            "test_user_new_format", username="test", password="password"
        )
        self.assertEqual(mock_log_into_pacer.call_count, 0)
        self.assertIsInstance(session_data, SessionData)
        self.assertEqual(session_data.proxy_address, "http://proxy_1:9090")

    @patch("cl.lib.pacer_session.log_into_pacer")
    def test_compute_cookies_for_almost_expired_data(
        self, mock_log_into_pacer
    ):
        """Are we using the dataclass when re-computing session?"""
        mock_log_into_pacer.return_value = SessionData(
            self.test_cookies, "http://proxy_2:9090"
        )

        # Attempts to get almost expired cookies with the new format from cache
        # Expects refresh.
        session_data = async_to_sync(get_or_cache_pacer_cookies)(
            "test_new_format_almost_expired",
            username="test",
            password="password",
        )
        self.assertIsInstance(session_data, SessionData)
        self.assertEqual(mock_log_into_pacer.call_count, 1)
        self.assertEqual(session_data.proxy_address, "http://proxy_2:9090")


class TestStringUtils(SimpleTestCase):
    def test_trunc(self) -> None:
        """Does trunc give us the results we expect?"""

        class TestType(TypedDict, total=False):
            length: int
            result: str
            ellipsis: str

        s = "Henry wants apple."
        tests: tuple[TestType, ...] = (
            # Simple case
            {"length": 13, "result": "Henry wants"},
            # Off by one cases
            {"length": 4, "result": "Henr"},
            {"length": 5, "result": "Henry"},
            {"length": 6, "result": "Henry"},
            # Do we include the length of the ellipsis when measuring?
            {"length": 12, "ellipsis": "...", "result": "Henry..."},
            # What happens when an alternate ellipsis is used instead?
            {"length": 15, "ellipsis": "....", "result": "Henry wants...."},
            # Do we cut properly when no spaces are found?
            {"length": 2, "result": "He"},
            # Do we cut properly when ellipsizing if no spaces found?
            {"length": 6, "ellipsis": "...", "result": "Hen..."},
            # Do we return the whole s when length >= s?
            {"length": 50, "result": s},
        )
        for test_dict in tests:
            result = trunc(
                s=s,
                length=test_dict["length"],
                ellipsis=test_dict.get("ellipsis", None),
            )
            self.assertEqual(
                result,
                test_dict["result"],
                msg="Failed with dict: {}.\n{} != {}".format(
                    test_dict, result, test_dict["result"]
                ),
            )
            self.assertTrue(
                len(result) <= test_dict["length"],
                msg="Failed with dict: {}.\n{} is longer than {}".format(
                    test_dict, result, test_dict["length"]
                ),
            )

    def test_anonymize(self) -> None:
        """Can we properly anonymize SSNs, EINs, and A-Numbers?"""
        # Simple cases. Anonymize them.
        self.assertEqual(anonymize("111-11-1111"), ("XXX-XX-XXXX", True))
        self.assertEqual(anonymize("11-1111111"), ("XX-XXXXXXX", True))
        self.assertEqual(anonymize("A11111111"), ("AXXXXXXXX", True))
        self.assertEqual(anonymize("A111111111"), ("AXXXXXXXX", True))

        # Starting or ending with letters isn't an SSN
        self.assertEqual(anonymize("A111-11-1111"), ("A111-11-1111", False))
        self.assertEqual(anonymize("111-11-1111A"), ("111-11-1111A", False))

        # Matches in a sentence
        self.assertEqual(
            anonymize("Term 111-11-1111 Term"),
            ("Term XXX-XX-XXXX Term", True),
        )
        self.assertEqual(
            anonymize("Term 11-1111111 Term"), ("Term XX-XXXXXXX Term", True)
        )
        self.assertEqual(
            anonymize("Term A11111111 Term"), ("Term AXXXXXXXX Term", True)
        )

        # Multiple matches
        self.assertEqual(
            anonymize("Term 111-11-1111 Term 111-11-1111 Term"),
            ("Term XXX-XX-XXXX Term XXX-XX-XXXX Term", True),
        )

    def test_dash_handling(self) -> None:
        """Can we convert dashes nicely?"""
        tests = {
            "en dash –": "en dash -",  # En-dash
            "em dash —": "em dash -",  # Em-dash
            "dash -": "dash -",  # Regular dash
        }
        for test, answer in tests.items():
            computed = normalize_dashes(test)
            self.assertEqual(computed, answer)


class TestModelHelpers(TestCase):
    """Test the model_utils helper functions"""

    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        self.court = Court.objects.get(pk="test")
        self.docket = Docket(case_name="Docket", court=self.court)
        self.opinioncluster = OpinionCluster(
            case_name="Hotline Bling",
            docket=self.docket,
            date_filed=datetime.date(2015, 12, 14),
        )
        self.opinion = Opinion(
            cluster=self.opinioncluster, type="Lead Opinion"
        )

    def test_make_upload_path_works_with_opinions(self) -> None:
        expected = "mp3/2015/12/14/hotline_bling.mp3"
        self.opinion.file_with_date = datetime.date(2015, 12, 14)
        path = make_upload_path(self.opinion, "hotline_bling.mp3")
        self.assertEqual(expected, path)

    def test_making_docket_number_core(self) -> None:
        expected = "1201032"
        self.assertEqual(
            make_docket_number_core("2:12-cv-01032-JKG-MJL"), expected
        )
        self.assertEqual(
            make_docket_number_core("12-cv-01032-JKG-MJL"), expected
        )
        self.assertEqual(make_docket_number_core("2:12-cv-01032"), expected)
        self.assertEqual(make_docket_number_core("12-cv-01032"), expected)
        self.assertEqual(
            make_docket_number_core(
                "CIVIL ACTION NO. 7:17\u2013CV\u201300426"
            ),
            "1700426",
        )
        self.assertEqual(
            make_docket_number_core("Case No.1:19-CV-00118-MRB"), "1900118"
        )

        # Do we automatically zero-pad short docket numbers?
        self.assertEqual(make_docket_number_core("12-cv-1032"), expected)

        # Case type up to 5 letters.
        self.assertEqual(
            make_docket_number_core("4:25-crcor-00029"), "2500029"
        )

        # bankruptcy numbers
        self.assertEqual(make_docket_number_core("12-33112"), "12033112")
        self.assertEqual(make_docket_number_core("12-00001"), "12000001")
        self.assertEqual(make_docket_number_core("12-0001"), "12000001")
        self.assertEqual(make_docket_number_core("06-10672-DHW"), "06010672")

        # docket_number fields can be null. If so, the core value should be
        # an empty string.
        self.assertEqual(make_docket_number_core(None), "")

    def test_avoid_generating_docket_number_core(self) -> None:
        """Can we avoid generating docket_number_core when the docket number
        format doesn't match a valid format or if a string contains more than
        one docket number?
        """

        # Not valid docket number formats for district, bankruptcy or appellate
        self.assertEqual(make_docket_number_core("Nos. C 123-80-123-82"), "")
        self.assertEqual(make_docket_number_core("Nos. C 123-80-123"), "")
        self.assertEqual(
            make_docket_number_core("Nos. 212-213, Dockets 27264, 27265"), ""
        )

        # Multiple valid docket numbers
        self.assertEqual(
            make_docket_number_core(
                "Nos. 14-13542, 14-13657, 15-10967, 15-11166"
            ),
            "",
        )
        self.assertEqual(make_docket_number_core("12-33112, 12-33112"), "")
        self.assertEqual(
            make_docket_number_core(
                "CIVIL ACTION NO. 7:17-CV-00426,  7:17-CV-00426"
            ),
            "",
        )

    def test_clean_docket_number(self) -> None:
        """Can we clean and return a docket number if it has a valid format?"""
        test_cases = {
            # Not valid docket number formats for district, bankruptcy or appellate
            # no docket number returned
            "Nos. C 123-80-123-82": "",
            "Nos. C 123-80-123": "",
            "Nos. 212-213": "",
            # Multiple valid docket numbers, no docket number returned
            "Nos. 14-13542, 14-13657, 15-10967, 15-11166": "",
            "12-33112, 12-33112": "",
            # One valid docket number, return the cleaned number
            "CIVIL ACTION NO. 7:17-CV-00426": "7:17-cv-00426",
            "Case No.1:19-CV-00118-MRB": "1:19-cv-00118",
            "Case 12-33112": "12-33112",
            "12-33112": "12-33112",
            "12-cv-01032-JKG-MJL": "12-cv-01032",
            "Nos. 212-213, Dockets 27264, 27265": "",
            "Nos. 12-213, Dockets 27264, 27265": "12-213",
            # SCOTUS A Dockets.
            "Docket: 16A989": "16a989",
            "Case  17A80": "17a80",
        }

        for raw, expected in test_cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(clean_docket_number(raw), expected)

    def test_is_docket_number(self) -> None:
        """Test is_docket_number method correctly detects a docket number."""

        self.assertEqual(is_docket_number("1:21-cv-1234-ABC"), True)
        self.assertEqual(is_docket_number("1:21-cv-1234"), True)
        self.assertEqual(is_docket_number("1:21-bk-1234"), True)
        self.assertEqual(is_docket_number("21-1234"), True)
        self.assertEqual(is_docket_number("21-cv-1234"), True)
        self.assertEqual(is_docket_number("21 1234"), False)
        self.assertEqual(is_docket_number("14 august"), False)
        self.assertEqual(is_docket_number("21-string"), False)
        self.assertEqual(is_docket_number("string-2134"), False)
        self.assertEqual(is_docket_number("21"), False)

    def test_making_scotus_docket_number_core(self) -> None:
        """Test make_scotus_docket_number_core method correctly creates
        docket number core for scotus dockets.
        """

        test_cases = [
            # None or empty inputs
            (None, ""),
            ("", ""),
            # SCOTUS A dockets
            ("16A985", "16A00985"),
            ("16a985", "16A00985"),
            ("22A1", "22A00001"),
            ("22A12345", "22A12345"),
            # SCOTUS appellate style docket numbers (YY-NNNNNN)
            ("12-33112", "12033112"),
            ("12-000001", "12000001"),
            ("06-10672", "06010672"),
            # Non-matching SCOTUS docket numbers
            ("23-cv-001", ""),
        ]

        for input_value, expected in test_cases:
            with self.subTest(input=input_value, expected=expected):
                self.assertEqual(
                    make_scotus_docket_number_core(input_value), expected
                )


class S3PrivateUUIDStorageTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket = DocketFactory.create()

    def test_file_save_with_path(self) -> None:
        """Does saving a file create directories and filenames correctly?"""
        pf = PacerHtmlFiles(
            content_object=self.docket,
            upload_type=UPLOAD_TYPE.DOCKET,
        )
        pf.filepath.save("test.html", ContentFile(b"asdf"))
        self.assertIn("recap-data/", pf.filepath.name)
        self.assertIn(".html", pf.filepath.name)


class TestMimeLookup(SimpleTestCase):
    """Test the Mime type lookup function(s)"""

    def test_unsupported_extension_returns_octetstream(self) -> None:
        """For a bad extension, do we return the proper default?"""
        tests = [
            "/var/junk/filename.something.xyz",
            "../var/junk/~filename_something",
            "../../junk.junk.xxx",
        ]
        for test in tests:
            self.assertEqual(
                "application/octet-stream", lookup_mime_type(test)
            )

    def test_known_good_mimetypes(self) -> None:
        """For known good mimetypes, make sure we return the right value"""
        tests = {
            "mp3/2015/1/1/something_v._something_else.mp3": "audio/mpeg",
            "doc/2015/1/1/voutila_v._bonvini.doc": "application/msword",
            "pdf/2015/1/1/voutila_v._bonvini.pdf": "application/pdf",
            "txt/2015/1/1/voutila_v._bonvini.txt": "text/plain",
        }
        for test_path in tests.keys():
            self.assertEqual(tests.get(test_path), lookup_mime_type(test_path))


class TestPACERPartyParsing(SimpleTestCase):
    """Various tests for the PACER party parsers."""

    def test_attorney_role_normalization(self) -> None:
        """Can we normalize the attorney roles into a small number of roles?"""
        pairs = [
            {
                "q": "(Inactive)",
                "a": {
                    "role": Role.INACTIVE,
                    "date_action": None,
                    "role_raw": "(Inactive)",
                },
            },
            {
                "q": "ATTORNEY IN SEALED GROUP",
                "a": {
                    "role": Role.ATTORNEY_IN_SEALED_GROUP,
                    "date_action": None,
                    "role_raw": "ATTORNEY IN SEALED GROUP",
                },
            },
            {
                "q": "ATTORNEY TO BE NOTICED",
                "a": {
                    "role": Role.ATTORNEY_TO_BE_NOTICED,
                    "date_action": None,
                    "role_raw": "ATTORNEY TO BE NOTICED",
                },
            },
            {
                "q": "Bar Status: ACTIVE",
                "a": {
                    "role": None,
                    "date_action": None,
                    "role_raw": "Bar Status: ACTIVE",
                },
            },
            {
                "q": "DISBARRED 02/19/2010",
                "a": {
                    "role": Role.DISBARRED,
                    "date_action": datetime.date(2010, 2, 19),
                    "role_raw": "DISBARRED 02/19/2010",
                },
            },
            {
                "q": "Designation: ADR Pro Bono Limited Scope Counsel",
                "a": {
                    "role": None,
                    "date_action": None,
                    "role_raw": "Designation: ADR Pro Bono Limited Scope "
                    "Counsel",
                },
            },
            {
                "q": "LEAD ATTORNEY",
                "a": {
                    "role": Role.ATTORNEY_LEAD,
                    "date_action": None,
                    "role_raw": "LEAD ATTORNEY",
                },
            },
            {
                "q": "PRO HAC VICE",
                "a": {
                    "role": Role.PRO_HAC_VICE,
                    "date_action": None,
                    "role_raw": "PRO HAC VICE",
                },
            },
            {
                "q": "SELF- TERMINATED: 01/14/2013",
                "a": {
                    "role": Role.SELF_TERMINATED,
                    "date_action": datetime.date(2013, 1, 14),
                    "role_raw": "SELF- TERMINATED: 01/14/2013",
                },
            },
            {
                "q": "SUSPENDED 01/22/2016",
                "a": {
                    "role": Role.SUSPENDED,
                    "date_action": datetime.date(2016, 1, 22),
                    "role_raw": "SUSPENDED 01/22/2016",
                },
            },
            {
                "q": "TERMINATED: 01/01/2007",
                "a": {
                    "role": Role.TERMINATED,
                    "date_action": datetime.date(2007, 1, 1),
                    "role_raw": "TERMINATED: 01/01/2007",
                },
            },
            {
                "q": "Blagger jabber",
                "a": {
                    "role": None,
                    "date_action": None,
                    "role_raw": "Blagger jabber",
                },
            },
        ]
        for pair in pairs:
            print(
                f"Normalizing PACER role of '{pair['q']}' to '{pair['a']}'...",
                end="",
            )
            result = normalize_attorney_role(cast(str, pair["q"]))
            self.assertEqual(result, pair["a"])
            print("✓")

    def test_state_normalization(self) -> None:
        pairs = [
            {"q": "CA", "a": "CA"},
            {"q": "ca", "a": "CA"},
            {"q": "California", "a": "CA"},
            {"q": "california", "a": "CA"},
        ]
        for pair in pairs:
            print(
                f"Normalizing state of '{pair['q']}' to '{pair['a']}'...",
                end="",
            )
            result = normalize_us_state(pair["q"])
            self.assertEqual(result, pair["a"])
            print("✓")

    def test_normalize_atty_contact(self) -> None:
        pairs = [
            {
                # Email and phone number
                "q": "Landye Bennett Blumstein LLP\n"
                "701 West Eighth Avenue, Suite 1200\n"
                "Anchorage, AK 99501\n"
                "907-276-5152\n"
                "Email: brucem@lbblawyers.com",
                "a": (
                    {
                        "name": "Landye Bennett Blumstein LLP",
                        "address1": "701 West Eighth Ave.",
                        "address2": "Suite 1200",
                        "city": "Anchorage",
                        "state": "AK",
                        "zip_code": "99501",
                        "lookup_key": "701westeighthavesuite1200anchoragelandyebennettblumsteinak99501",
                    },
                    {
                        "email": "brucem@lbblawyers.com",
                        "phone": "(907) 276-5152",
                        "fax": "",
                    },
                ),
            },
            {
                # PO Box
                "q": "Sands Anderson PC\n"
                "P.O. Box 2188\n"
                "Richmond, VA 23218-2188\n"
                "(804) 648-1636",
                "a": (
                    {
                        "name": "Sands Anderson PC",
                        "address1": "P.O. Box 2188",
                        "city": "Richmond",
                        "state": "VA",
                        "zip_code": "23218-2188",
                        "lookup_key": "pobox2188richmondsandsandersonva232182188",
                    },
                    {
                        "phone": "(804) 648-1636",
                        "fax": "",
                        "email": "",
                    },
                ),
            },
            {
                # Lowercase state (needs normalization)
                "q": "Sands Anderson PC\n"
                "P.O. Box 2188\n"
                "Richmond, va 23218-2188\n"
                "(804) 648-1636",
                "a": (
                    {
                        "name": "Sands Anderson PC",
                        "address1": "P.O. Box 2188",
                        "city": "Richmond",
                        "state": "VA",
                        "zip_code": "23218-2188",
                        "lookup_key": "pobox2188richmondsandsandersonva232182188",
                    },
                    {
                        "phone": "(804) 648-1636",
                        "fax": "",
                        "email": "",
                    },
                ),
            },
            {
                # Phone, fax, and email -- the whole package.
                "q": "Susman Godfrey, LLP\n"
                "1201 Third Avenue, Suite 3800\n"
                "Seattle, WA 98101\n"
                "206-373-7381\n"
                "Fax: 206-516-3883\n"
                "Email: fshort@susmangodfrey.com",
                "a": (
                    {
                        "name": "Susman Godfrey, LLP",
                        "address1": "1201 Third Ave.",
                        "address2": "Suite 3800",
                        "city": "Seattle",
                        "state": "WA",
                        "zip_code": "98101",
                        "lookup_key": "1201thirdavesuite3800seattlesusmangodfreywa98101",
                    },
                    {
                        "phone": "(206) 373-7381",
                        "fax": "(206) 516-3883",
                        "email": "fshort@susmangodfrey.com",
                    },
                ),
            },
            {
                # No recipient name
                "q": "211 E. Livingston Ave\n"
                "Columbus, OH 43215\n"
                "(614) 228-3727\n"
                "Email:",
                "a": (
                    {
                        "address1": "211 E. Livingston Ave",
                        "city": "Columbus",
                        "state": "OH",
                        "zip_code": "43215",
                        "lookup_key": "211elivingstonavecolumbusoh43215",
                    },
                    {
                        "phone": "(614) 228-3727",
                        "email": "",
                        "fax": "",
                    },
                ),
            },
            {
                # Weird ways of doing phone numbers
                "q": """1200 Boulevard Tower
                    1018 Kanawha Boulevard, E
                    Charleston, WV 25301
                    304/342-3174
                    Fax: 304/342-0448
                    Email: caglelaw@aol.com
                """,
                "a": (
                    {
                        "address1": "1018 Kanawha Blvd., E",
                        "address2": "1200 Blvd. Tower",
                        "city": "Charleston",
                        "state": "WV",
                        "zip_code": "25301",
                        "lookup_key": "1018kanawhablvde1200blvdtowercharlestonwv25301",
                    },
                    {
                        "phone": "(304) 342-3174",
                        "fax": "(304) 342-0448",
                        "email": "caglelaw@aol.com",
                    },
                ),
            },
            {
                # Empty fax numbers (b/c PACER).
                "q": """303 E 17th Ave
                    Suite 300
                    Denver, CO 80203
                    303-861-1764
                    Fax:
                    Email: jeff@dyerberens.com
            """,
                "a": (
                    {
                        "address1": "303 E 17th Ave",
                        "address2": "Suite 300",
                        "city": "Denver",
                        "state": "CO",
                        "zip_code": "80203",
                        "lookup_key": "303e17thavesuite300denverco80203",
                    },
                    {
                        "phone": "(303) 861-1764",
                        "fax": "",
                        "email": "jeff@dyerberens.com",
                    },
                ),
            },
            {
                # Funky phone number
                "q": """Guerrini Law Firm
                    106 SOUTH MENTOR AVE. #150
                    Pasadena, CA 91106
                    626-229-9611-202
                    Fax: 626-229-9615
                    Email: guerrini@guerrinilaw.com
                """,
                "a": (
                    {
                        "name": "Guerrini Law Firm",
                        "address1": "106 South Mentor Ave.",
                        "address2": "# 150",
                        "city": "Pasadena",
                        "state": "CA",
                        "zip_code": "91106",
                        "lookup_key": "106southmentorave150pasadenaguerrinilawfirmca91106",
                    },
                    {
                        "phone": "",
                        "fax": "(626) 229-9615",
                        "email": "guerrini@guerrinilaw.com",
                    },
                ),
            },
            {
                "q": """Duncan & Sevin, LLC
                    400 Poydras St.
                    Suite 1200
                    New Orleans, LA 70130
                """,
                "a": (
                    {
                        "name": "Duncan & Sevin, LLC",
                        "address1": "400 Poydras St.",
                        "address2": "Suite 1200",
                        "city": "New Orleans",
                        "state": "LA",
                        "zip_code": "70130",
                        "lookup_key": "400poydrasstsuite1200neworleansduncansevinllcla70130",
                    },
                    {
                        "phone": "",
                        "fax": "",
                        "email": "",
                    },
                ),
            },
            {
                # Ambiguous address. Returns empty dict.
                "q": """Darden, Koretzky, Tessier, Finn, Blossman & Areaux
                    Energy Centre
                    1100 Poydras Street
                    Suite 3100
                    New Orleans, LA 70163
                    504-585-3800
                    Email: darden@carverdarden.com
                """,
                "a": (
                    {},
                    {
                        "phone": "(504) 585-3800",
                        "email": "darden@carverdarden.com",
                        "fax": "",
                    },
                ),
            },
            {
                # Ambiguous address with unicode that triggers
                # https://github.com/datamade/probableparsing/issues/2
                "q": """Darden, Koretzky, Tessier, Finn, Blossman & Areaux
                    Energy Centre
                    1100 Poydras Street
                    Suite 3100
                    New Orléans, LA 70163
                    504-585-3800
                    Email: darden@carverdarden.com
                """,
                "a": (
                    {},
                    {
                        "phone": "(504) 585-3800",
                        "email": "darden@carverdarden.com",
                        "fax": "",
                    },
                ),
            },
            {
                # Missing zip code, phone number ambiguously used instead.
                "q": """NSB - Department of Law
                    POB 69
                    Barrow, AK 907-852-0300
                """,
                "a": (
                    {
                        "name": "NSB Department of Law",
                        "address1": "Pob 69",
                        "city": "Barrow",
                        "state": "AK",
                        "zip_code": "",
                        "lookup_key": "pob69barrownsbdepartmentoflawak",
                    },
                    {
                        "phone": "",
                        "fax": "",
                        "email": "",
                    },
                ),
            },
            {
                # Unknown/invalid state.
                "q": """Kessler Topaz Meltzer Check LLP
                    280 King of Prussia Road
                    Radnor, OA 19087
                    (610) 667-7706
                    Fax: (610) 667-7056
                    Email: jneumann@ktmc.com
                """,
                "a": (
                    {
                        "name": "Kessler Topaz Meltzer Check LLP",
                        "city": "Radnor",
                        "address1": "280 King of Prussia Road",
                        "lookup_key": "280kingofprussiaroadradnorkesslertopazmeltzercheck19087",
                        "state": "",
                        "zip_code": "19087",
                    },
                    {
                        "phone": "(610) 667-7706",
                        "fax": "(610) 667-7056",
                        "email": "jneumann@ktmc.com",
                    },
                ),
            },
        ]
        for i, pair in enumerate(pairs):
            print(f"Normalizing address {i}...", end="")
            result = normalize_attorney_contact(pair["q"])  # type: ignore
            self.maxDiff = None
            self.assertEqual(result, pair["a"])  # type: ignore
            print("✓")

    def test_making_a_lookup_key(self) -> None:
        self.assertEqual(
            make_address_lookup_key(
                {
                    "address1": "400 Poydras St.",
                    "address2": "Suite 1200",
                    "city": "New Orleans",
                    "name": "Duncan and Sevin, LLC",
                    "state": "LA",
                    "zip_code": "70130",
                }
            ),
            "400poydrasstsuite1200neworleansduncansevinllcla70130",
        )
        self.assertEqual(
            make_address_lookup_key(
                {"name": "Offices of Lissner AND Strook & Levin, LLP"}
            ),
            "officeoflissnerstrooklevin",
        )


class TestFilesizeConversions(SimpleTestCase):
    def test_filesize_conversions(self) -> None:
        """Can we convert human filesizes to bytes?"""
        qa_pairs = [
            ("58 kb", 59392),
            ("117 kb", 119808),
            ("117kb", 119808),
            ("1 byte", 1),
            ("117 bytes", 117),
            ("117  bytes", 117),
            ("  117 bytes  ", 117),
            ("117b", 117),
            ("117bytes", 117),
            ("1 kilobyte", 1024),
            ("117 kilobytes", 119808),
            ("0.7 mb", 734003),
            ("1mb", 1048576),
            ("5.2 mb", 5452595),
        ]
        for qa in qa_pairs:
            print(f"Converting '{qa[0]}' to bytes...", end="")
            self.assertEqual(convert_size_to_bytes(qa[0]), qa[1])
            print("✓")


class TestRateLimiters(SimpleTestCase):
    def test_parsing_rates(self) -> None:
        qa_pairs = [
            ("1/s", (1, 1)),
            ("10/10s", (10, 10)),
            ("1/m", (1, 60)),
            ("1/5m", (1, 300)),
        ]
        for q, a in qa_pairs:
            with self.subTest("Parsing rates...", rate=q):
                self.assertEqual(parse_rate(q), a)


class TestFactoriesClasses(TestCase):
    def test_related_factory_variable_list(self):
        court_scotus = CourtFactory(id="scotus")

        # Create 3 opinions by default
        cluster_1 = OpinionClusterWithMultipleOpinionsFactory(
            docket=DocketFactory(
                court=court_scotus,
                case_name="Foo v. Bar",
                case_name_full="Foo v. Bar",
            ),
            case_name="Foo v. Bar",
            date_filed=datetime.date.today(),
        )

        # Check that 3 opinions were created
        self.assertEqual(cluster_1.sub_opinions.all().count(), 3)

        # Create 3 opinions specifying type for each one
        cluster_2 = OpinionClusterWithMultipleOpinionsFactory(
            docket=DocketFactory(
                court=court_scotus,
                case_name="Lorem v. Ipsum",
                case_name_full="Lorem v. Ipsum",
            ),
            case_name="Lorem v. Ipsum",
            date_filed=datetime.date.today(),
            sub_opinions__data=[
                {"type": "010combined"},
                {"type": "025plurality"},
                {"type": "070rehearing"},
            ],
        )

        # Check that 3 opinions were created
        self.assertEqual(cluster_2.sub_opinions.all().count(), 3)

        # Check that each created opinion matches the specified type
        self.assertEqual(
            cluster_2.sub_opinions.all().order_by("type")[0].type,
            "010combined",
        )
        self.assertEqual(
            cluster_2.sub_opinions.all().order_by("type")[1].type,
            "025plurality",
        )
        self.assertEqual(
            cluster_2.sub_opinions.all().order_by("type")[2].type,
            "070rehearing",
        )


class TestDateTimeHelpers(SimpleTestCase):
    def test_midnight_pt(self) -> None:
        # Date in PSD time -8 hours UTC offset
        pst_date = datetime.date(2023, 1, 3)
        pst_date_time = midnight_pt(pst_date)
        pst_utc_offset_hours = pst_date_time.utcoffset().total_seconds() / 3600  # type: ignore
        self.assertEqual(pst_utc_offset_hours, -8.0)

        # Date in PDT time -7 hours UTC offset
        pdt_date = datetime.date(2023, 5, 3)
        pdt_date_time = midnight_pt(pdt_date)
        pdt_utc_offset_hours = pdt_date_time.utcoffset().total_seconds() / 3600  # type: ignore
        self.assertEqual(pdt_utc_offset_hours, -7.0)


class TestElasticsearchUtils(SimpleTestCase):
    def test_can_add_conjunction(self) -> None:
        tests = [
            {"input": "a", "output": "a"},
            {"input": "a b", "output": "a AND b"},
            {"input": "a b (c d)", "output": "a AND b AND (c d)"},
            {
                "input": "caseName:Loretta AND docketNumber:(ASBCA No. 59126)",
                "output": "caseName:Loretta AND docketNumber:(ASBCA No. 59126)",
            },
            {
                "input": "a b (c d) [a b]",
                "output": "a AND b AND (c d) AND [a b]",
            },
            {
                "input": 'a b (c d) [a b] "a c"',
                "output": 'a AND b AND (c d) AND [a b] AND "a c"',
            },
            {
                "input": "a b (c d) [a b] NOT word1",
                "output": "a AND b AND (c d) AND [a b] AND NOT word1",
            },
            {
                "input": 'a b NOT word1 (c d) [a b] NOT (word1 word2) "a z" NOT [word3 word4]',
                "output": 'a AND b AND NOT word1 AND (c d) AND [a b] AND NOT (word1 word2) AND "a z" AND NOT [word3 word4]',
            },
            {
                "input": 'a b NOT a (c d) [a b] NOT (a w) "a z" word1 AND word2',
                "output": 'a AND b AND NOT a AND (c d) AND [a b] AND NOT (a w) AND "a z" AND word1 AND word2',
            },
            {
                "input": 'a b NOT a (c d) [a b] AND (a w) "a z" word1 OR word2',
                "output": 'a AND b AND NOT a AND (c d) AND [a b] AND (a w) AND "a z" AND word1 OR word2',
            },
            {
                "input": "(A AND B) (a bc (a b)) and word1",
                "output": "(A AND B) AND (a bc (a b)) and word1",
            },
            {
                "input": 'field:"a w c" (a bc (a b) and w) and docket:"word1 word3"',
                "output": 'field:"a w c" AND (a bc (a b) and w) and docket:"word1 word3"',
            },
        ]

        for test in tests:
            ouput_str = append_query_conjunctions(test["input"])
            self.assertEqual(ouput_str, test["output"])

    def test_check_and_sanitize_queries_bad_syntax(self) -> None:
        """Tests for methods that check and sanitize queries with a bad search
        syntax.
        """

        # Check for bad proximity tokens.
        tests = [
            {
                "input_str": "This is a range /p query",
                "output": True,
            },
            {
                "input_str": "This is a range /s query",
                "output": True,
            },
            {
                "input_str": "This is a range/s query",
                "output": True,
            },
            {
                "input_str": "This is a range/p query",
                "output": True,
            },
            {
                "input_str": "This is a /s range /p query",
                "output": True,
            },
            {
                "input_str": "This is not a range query",
                "output": False,
            },
            {
                "input_str": "This is no proximity /short query",
                "output": False,
            },
            {
                "input_str": "This is no proximity /parent query",
                "output": False,
            },
            {
                "input_str": "This is no proximity long/short query",
                "output": False,
            },
            {
                "input_str": "This is no proximity long/parent query",
                "output": False,
            },
        ]
        for test in tests:
            output = check_for_proximity_tokens(test["input_str"])  # type: ignore
            self.assertEqual(output, test["output"])

        # Check for Unbalanced parentheses.
        tests = [
            {
                "input_str": "This is (unbalanced",
                "output": True,
                "sanitized": "This is unbalanced",
            },
            {
                "input_str": "This is unbalanced)",
                "output": True,
                "sanitized": "This is unbalanced",
            },
            {
                "input_str": "This is (unbalanced)(",
                "output": True,
                "sanitized": "This is (unbalanced)",
            },
            {
                "input_str": "This (is (unbalanced)(",
                "output": True,
                "sanitized": "This (is unbalanced)",
            },
            {
                "input_str": "This (is (unbalanced)()",
                "output": True,
                "sanitized": "This (is (unbalanced))",
            },
            {
                "input_str": "(This) (is (balanced))",
                "output": False,
                "sanitized": "(This) (is (balanced))",
            },
        ]
        for test in tests:
            output = check_unbalanced_parenthesis(test["input_str"])  # type: ignore
            self.assertEqual(output, test["output"])

        for test in tests:
            output = sanitize_unbalanced_parenthesis(test["input_str"])  # type: ignore
            self.assertEqual(output, test["sanitized"])

        # Check for Unbalanced quotes.
        tests = [
            {
                "input_str": 'This is "unbalanced',
                "output": True,
                "sanitized": "This is unbalanced",
            },
            {
                "input_str": "This is “unbalanced",
                "output": True,
                "sanitized": "This is unbalanced",
            },
            {
                "input_str": 'This is "unbalanced""',
                "output": True,
                "sanitized": 'This is "unbalanced"',
            },
            {
                "input_str": "This is “unbalanced””",
                "output": True,
                "sanitized": 'This is "unbalanced"',
            },
            {
                "input_str": 'This "is" unbalanced"',
                "output": True,
                "sanitized": 'This "is" unbalanced',
            },
            {
                "input_str": 'This "is” unbalanced"',
                "output": True,
                "sanitized": 'This "is" unbalanced',
            },
            {
                "input_str": 'This "is" unbalanced"""',
                "output": True,
                "sanitized": 'This "is" unbalanced""',
            },
            {
                "input_str": '"This is" "balanced"',
                "output": False,
                "sanitized": '"This is" "balanced"',
            },
        ]
        for test in tests:
            output = check_unbalanced_quotes(test["input_str"])  # type: ignore
            self.assertEqual(output, test["output"])

        for test in tests:
            output = sanitize_unbalanced_quotes(test["input_str"])  # type: ignore
            self.assertEqual(output, test["sanitized"])

    def test_can_get_parties_from_bankruptcy_case_name(self) -> None:
        class PartiesNameTestType(TypedDict):
            case_name: str
            output: list[str]

        tests: list[PartiesNameTestType] = [
            {
                "case_name": "Mendelsohn. Singh",
                "output": ["Mendelsohn. Singh"],
            },
            {
                "case_name": "Cadle Co. v Matos",
                "output": ["Cadle Co.", "Matos"],
            },
            {
                "case_name": "Cadle Co. v Matos",
                "output": ["Cadle Co.", "Matos"],
            },
            {
                "case_name": "Cadle Co. v. Matos",
                "output": ["Cadle Co.", "Matos"],
            },
            {
                "case_name": "Cadle Co. vs Matos",
                "output": ["Cadle Co.", "Matos"],
            },
            {
                "case_name": "Cadle Co. vs. Matos",
                "output": ["Cadle Co.", "Matos"],
            },
            {
                "case_name": "Paul Thomas Presbury, Jr. and Lisa Rae Presbury",
                "output": ["Paul Thomas Presbury, Jr.", "Lisa Rae Presbury"],
            },
            {
                "case_name": "Ma Margarita Bernal Sosa -ABOVE MED",
                "output": ["Ma Margarita Bernal Sosa"],
            },
            {
                "case_name": "Jennifer Renee' Abbott and Quentin Andrew Abbott -ABOVE MED",
                "output": ["Jennifer Renee' Abbott", "Quentin Andrew Abbott"],
            },
            {
                "case_name": "Aiesha Renee -BELOW MED",
                "output": ["Aiesha Renee"],
            },
            {
                "case_name": "Justin Kaiser and Belinda Kaiser -BELOW MED",
                "output": ["Justin Kaiser", "Belinda Kaiser"],
            },
            {
                "case_name": "Cosmorex Ltd. (in Liquidation)",
                "output": ["Cosmorex Ltd."],
            },
            {
                "case_name": "Cowen & Co. v. Zagar (In re Zagar)",
                "output": ["Cowen & Co.", "Zagar"],
            },
            {
                "case_name": 'Advantage LLC <b><font color="red">Jointly Administered under 23-90886.</font></b>',
                "output": ["Advantage LLC"],
            },
            {
                "case_name": 'Sather v. Carlson<b><font color="red">DO NOT DOCKET. CASE TRANSFERRED OUT.</font></b>',
                "output": ["Sather", "Carlson"],
            },
            {
                "case_name": 'Saucedo and Green Dream International, LLC <b> <font color="red"> Case Consolidated under 23-03142 </font> </b>',
                "output": ["Saucedo", "Green Dream International, LLC"],
            },
            {
                "case_name": "In re: Matter of Nicholas M. Wajda",
                "output": [],
            },
            {
                "case_name": "In re Matter of Proof of Claim Replacement Filings",
                "output": [],
            },
            {
                "case_name": "In re T.H.",
                "output": [],
            },
            {
                "case_name": "In Re: Dempsey Clay Ward",
                "output": [],
            },
            {
                "case_name": "In re: Receivership of Horses and Equipment v. Gabriel",
                "output": [],
            },
            {
                "case_name": "In Re: Appearances of Attorney James G. ORourke in Pending Bankruptcy Cases",
                "output": [],
            },
            {
                "case_name": "In the matter of Attorney Rodney D. Shepherd",
                "output": [],
            },
            {
                "case_name": "Rochester Drug Cooperative, Inc. - Adversary Proceeding",
                "output": ["Rochester Drug Cooperative, Inc."],
            },
            {
                "case_name": "Ronald W. Howland, Jr and Marilee R Howland - Adversary Proceeding",
                "output": ["Ronald W. Howland, Jr", "Marilee R Howland"],
            },
            {
                "case_name": "Derrick D. Thomas v Kacy L. Thomas - Adversary Proceeding",
                "output": ["Derrick D. Thomas", "Kacy L. Thomas"],
            },
            {
                "case_name": "Unknown Case Title",
                "output": [],
            },
            {
                "case_name": "Unknown Case Title - Adversary Proceeding",
                "output": [],
            },
        ]
        for test in tests:
            with self.subTest(
                input=test["case_name"], msg="get parties names from case name"
            ):
                parties: list[str] = get_parties_from_case_name_bankr(
                    test["case_name"]
                )
                self.assertEqual(
                    parties,
                    test["output"],
                )


class TestRedisUtils(SimpleTestCase):
    """Test Redis utils functions."""

    def test_redis_lock(self) -> None:
        """Test acquiring and releasing a Redis lock."""

        lock_key = "test_lock"
        r = get_redis_interface("CACHE")
        identifier = acquire_redis_lock(r, lock_key, 2000)
        self.assertTrue(identifier)

        result = release_redis_lock(r, lock_key, identifier)
        self.assertEqual(result, 1)


class TestLinkifyOrigDocketNumber(SimpleTestCase):
    def test_linkify_orig_docket_number(self):
        test_pairs = [
            (
                "National Labor Relations Board",
                "19-CA-289275",
                "https://www.nlrb.gov/case/19-CA-289275",
            ),
            (
                "National Labor Relations Board",
                "NLRB-09CA110508",
                "https://www.nlrb.gov/case/09-CA-110508",
            ),
            (
                "EPA",
                "85 FR 20688",
                "https://www.federalregister.gov/citation/85-FR-20688",
            ),
            (
                "Other Agency",
                "85 Fed. Reg. 12345",
                "https://www.federalregister.gov/citation/85-FR-12345",
            ),
            (
                "National Labor Relations Board",
                "85 Fed. Reg. 12345",
                "https://www.federalregister.gov/citation/85-FR-12345",
            ),
            (
                "Bureau of Land Management",
                "88FR20688",
                "https://www.federalregister.gov/citation/88-FR-20688",
            ),
            (
                "Bureau of Land Management",
                "88 Fed Reg 34523",
                "https://www.federalregister.gov/citation/88-FR-34523",
            ),
            (
                "Department of Transportation",
                "89 Fed. Reg. 34,620",
                "https://www.federalregister.gov/citation/89-FR-34,620",
            ),
            (
                "Animal and Plant Health Inspection Service",
                "89 FR 106981",
                "https://www.federalregister.gov/citation/89-FR-106981",
            ),
            (
                "Animal and Plant Health Inspection Service",
                "89 Fed. Reg. 106,981",
                "https://www.federalregister.gov/citation/89-FR-106,981",
            ),
            (
                "Environmental Protection Agency",
                "EPA-HQ-OW-2020-0005",
                "https://www.regulations.gov/docket/EPA-HQ-OW-2020-0005",
            ),
            (
                "United States Tax Court",
                "USTC-2451-13",
                "https://dawson.ustaxcourt.gov/case-detail/02451-13",
            ),
            (
                "United States Tax Court",
                "6837-20",
                "https://dawson.ustaxcourt.gov/case-detail/06837-20",
            ),
            (
                "United States Tax Court",
                "USTC-5903-19W",
                "https://dawson.ustaxcourt.gov/case-detail/05903-19W",
            ),
            ("Federal Communications Commission", "19-CA-289275", ""),
            (
                "National Labor Relations Board",
                "This is not an NLRB case",
                "",
            ),
            ("Other Agency", "This is not a Federal Register citation", ""),
        ]

        for i, (agency, docket_number, expected_output) in enumerate(
            test_pairs
        ):
            with self.subTest(
                f"Testing description text cleaning for {agency, docket_number}...",
                i=i,
            ):
                self.assertEqual(
                    linkify_orig_docket_number(agency, docket_number),
                    expected_output,
                    f"Got incorrect result from clean_parenthetical_text for text: {agency, docket_number}",
                )


class TestAddSqlComment(SimpleTestCase):
    """Test the add_sql_comment function"""

    def test_no_metadata_returns_unchanged_sql(self) -> None:
        """Does an empty meta dict return the original SQL unchanged?"""
        sql = "SELECT * FROM users"
        result = add_sql_comment(sql)
        self.assertEqual(result, sql)

    def test_with_metadata_appends_comment(self) -> None:
        """Does metadata get appended as a SQL comment?"""
        sql = "SELECT * FROM users"
        result = add_sql_comment(sql, user_id=123, url="/test/path")
        self.assertIn("/* ", result)
        self.assertIn("user_id='123'", result)
        self.assertIn("url='/test/path'", result)
        self.assertIn(" */", result)

    def test_sql_ending_with_semicolon(self) -> None:
        """Is the comment inserted before the semicolon?"""
        sql = "SELECT * FROM users;"
        result = add_sql_comment(sql, user_id=42)
        self.assertTrue(result.endswith(";"))
        self.assertIn("/* user_id='42' */", result)

    def test_sql_not_ending_with_semicolon(self) -> None:
        """Is the comment appended at the end for SQL without semicolon?"""
        sql = "SELECT * FROM users"
        result = add_sql_comment(sql, user_id=42)
        self.assertFalse(result.endswith(";"))
        self.assertTrue(result.startswith("/* user_id='42' */"))

    def test_none_values_filtered_out(self) -> None:
        """Are None values filtered from the comment?"""
        sql = "SELECT * FROM users"
        result = add_sql_comment(sql, user_id=None, url="/test")
        self.assertNotIn("user_id", result)
        self.assertIn("url='/test'", result)

    def test_all_none_values_returns_unchanged(self) -> None:
        """Does all-None metadata return the original SQL unchanged?"""
        sql = "SELECT * FROM users"
        result = add_sql_comment(sql, user_id=None, url=None)
        self.assertEqual(result, sql)

    def test_sql_with_trailing_whitespace(self) -> None:
        """Is trailing whitespace handled correctly?"""
        sql = "SELECT * FROM users   "
        result = add_sql_comment(sql, user_id=1)
        self.assertIn("/* user_id='1' */", result)
        self.assertNotIn("   /*", result)

    def test_add_sql_comment_prevents_comment_closure_injection(self) -> None:
        sql = "SELECT * FROM users"
        malicious_path = "/test*/;DROP TABLE users;--"

        result = add_sql_comment(sql, url=malicious_path)

        # The injected terminator must NOT appear
        self.assertNotIn("*/;DROP TABLE", result)

        # SQL comment must still be intact
        self.assertEqual(result.count("/*"), 1)
        self.assertEqual(result.count("*/"), 1)

    def test_add_sql_comment_handles_newlines_safely(self) -> None:
        sql = "SELECT 1"
        path = "/test\n*/\nDROP TABLE users;"

        result = add_sql_comment(sql, url=path)

        self.assertNotIn("\nDROP TABLE", result)
        self.assertEqual(result.count("/*"), 1)
        self.assertEqual(result.count("*/"), 1)


class TestQueryWrapper(TestCase):
    """Test the QueryWrapper class"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.request_factory = RequestFactory()

    class MockResolverMatch:
        def __init__(self, view_name="test-view"):
            self.view_name = view_name

    def test_get_context_without_resolver_match(self) -> None:
        request = self.request_factory.get("/no-resolver/")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        self.assertIsNone(result["user_id"])
        self.assertIsNone(result["url"])
        self.assertIsNone(result["url-name"])

    def test_get_context_without_user(self) -> None:
        """Does get_context return None user_id when request has no user?"""
        request = self.request_factory.get("/test/path/")
        request.resolver_match = self.MockResolverMatch("test-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        self.assertIsNone(result["user_id"])
        self.assertEqual(result["url"], "/test/path/")
        self.assertEqual(result["url-name"], "test-view")

    def test_get_context_with_authenticated_user(self) -> None:
        """Does get_context return user_id and url for authenticated user?"""
        request = self.request_factory.get("/test/path/")
        request.user = self.user
        request.resolver_match = self.MockResolverMatch("test-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        self.assertIn("user_id", result)
        self.assertIn("url", result)
        self.assertEqual(result["url"], "/test/path/")
        self.assertEqual(result["user_id"], self.user.pk)
        self.assertEqual(result["url-name"], "test-view")

    def test_get_context_with_anonymous_user(self) -> None:
        """Does get_context handle anonymous user correctly?"""
        request = self.request_factory.get("/anonymous/path/")
        request.user = AnonymousUser()
        request.resolver_match = self.MockResolverMatch("anon-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        self.assertIsNone(result["user_id"])
        self.assertEqual(result["url"], "/anonymous/path/")
        self.assertEqual(result["url-name"], "anon-view")

    @override_settings(SQLCOMMENTER_MAX_PATH_LENGTH=10)
    def test_get_context_truncates_path(self):
        request = self.request_factory.get("/very/long/path/")
        request.user = self.user
        request.resolver_match = self.MockResolverMatch(view_name="test-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        self.assertEqual(result["url"], "/very/long…")

    def test_get_context_with_unevaluated_lazy_user(self) -> None:
        """Does get_context handle unevaluated SimpleLazyObject without recursion?

        When request.user is a SimpleLazyObject that hasn't been evaluated,
        accessing is_authenticated would trigger a database query to fetch
        the user. That query would go through the SQL commenter again, causing
        infinite recursion. This test verifies we handle this case correctly.
        """
        request = self.request_factory.get("/lazy/user/path/")
        # Create an unevaluated SimpleLazyObject (simulating Django's lazy user)
        request.user = SimpleLazyObject(lambda: self.user)
        request.resolver_match = self.MockResolverMatch("lazy-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        # User should be None since the lazy object hasn't been evaluated
        self.assertIsNone(result["user_id"])
        self.assertEqual(result["url"], "/lazy/user/path/")
        self.assertEqual(result["url-name"], "lazy-view")

    def test_get_context_with_evaluated_lazy_user(self) -> None:
        """Does get_context return user_id for an evaluated SimpleLazyObject?"""
        request = self.request_factory.get("/lazy/user/path/")
        lazy_user = SimpleLazyObject(lambda: self.user)
        # Force evaluation of the lazy object
        _ = lazy_user.pk  # type: ignore[attr-defined]
        request.user = lazy_user
        request.resolver_match = self.MockResolverMatch("lazy-view")

        wrapper = QueryWrapper(request)
        result = wrapper.get_context()

        # User should be set since the lazy object has been evaluated
        self.assertEqual(result["user_id"], self.user.pk)
        self.assertEqual(result["url"], "/lazy/user/path/")
        self.assertEqual(result["url-name"], "lazy-view")


class TestSqlCommenterMiddleware(TestCase):
    """Integration tests for SqlCommenter middleware"""

    class MockResolverMatch:
        def __init__(self, view_name="test-view"):
            self.view_name = view_name

    def test_middleware_adds_comment_to_queries(self) -> None:
        """Does the middleware add comments to database queries?"""
        mock_get_response = MagicMock(return_value="response")

        class MockRequest:
            path = "/test/"
            resolver_match = self.MockResolverMatch("test-view")

        middleware = SqlCommenter(mock_get_response)

        with patch("cl.lib.sqlcommenter.connections") as mock_connections:
            mock_db = MagicMock()
            mock_connections.__iter__ = MagicMock(
                return_value=iter(["default"])
            )
            mock_connections.__getitem__ = MagicMock(return_value=mock_db)

            result = middleware(MockRequest())

            self.assertEqual(result, "response")
            mock_get_response.assert_called_once()
            mock_db.execute_wrapper.assert_called_once()

    def test_query_wrapper_modifies_sql(self) -> None:
        """Does QueryWrapper correctly modify SQL before execution?"""

        class MockRequest:
            path = "/api/test/"
            resolver_match = self.MockResolverMatch("test-view")

        wrapper = QueryWrapper(MockRequest())

        mock_execute = MagicMock(return_value="result")
        mock_connection = MagicMock()
        context = {"connection": mock_connection}

        result = wrapper(
            mock_execute,
            "SELECT * FROM test_table",
            (),
            False,
            context,
        )

        self.assertEqual(result, "result")
        call_args = mock_execute.call_args
        modified_sql = call_args[0][0]
        self.assertIn("/* ", modified_sql)
        self.assertIn("url='/api/test/'", modified_sql)
        self.assertIn(" */", modified_sql)


@override_settings(CHARS_THRESHOLD_OCR_PER_PAGE=50)
class TestRecapUtils(SimpleTestCase):
    def test_needs_ocr_cacb_example(self):
        """Test needs_ocr function with multi-line headers from cacb example provided in issue #598

        This text contains headers like 'Case...', 'Doc...Filed...',
        'Main Document', and 'Desc'. The function should recognize these
        as non-content lines and return True (needs OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.cacb.1466705.1.0.pdf
        """
        cacb_text = """
Case 2:12-bk-17500-TD   Doc 1 Filed 03/01/12 Entered 03/01/12 12:14:26   Desc

Main Document Page 1 of 58


Case 2:12-bk-17500-TD

Doc 1 Filed 03/01/12 Entered 03/01/12 12:14:26
Main Document
Page 58 of 58

Desc


"""
        self.assertTrue(
            needs_ocr(cacb_text), msg="cacb example should need OCR"
        )

    def test_needs_ocr_cacd_example(self):
        """Test needs_ocr function with multi-line headers from cacd example provided in issue #598

        This text contains headers like 'Case...', 'Doc...Filed...',
        'Main Document', and 'Desc'. The function should recognize these
        as non-content lines and return True (needs OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.cacd.584625.9.0.pdf
        """
        cacd_text = """
Case
 Case9:13-bk-10313-RR
      2:14-cv-01681-DOCDoc
                         Document
                           138 Filed
                                  9 04/10/14
                                     Filed 04/10/14
                                                Entered
                                                     Page
                                                        04/10/14
                                                          1 of 22 15:07:33
                                                                   Page ID #:32
                                                                            Desc
                        Main Document     Page 1 of 22
Case
 Case9:13-bk-10313-RR
      2:14-cv-01681-DOCDoc
                         Document
                           138 Filed
                                  9 04/10/14
                                     Filed 04/10/14
                                                Entered
                                                     Page
                                                        04/10/14
                                                          2 of 22 15:07:33
                                                                   Page ID #:33
                                                                            Desc
                        Main Document     Page 2 of 22
"""
        self.assertTrue(
            needs_ocr(cacd_text), msg="cacd example should need OCR"
        )

    def test_needs_ocr_msnd_example(self):
        """Test needs_ocr function with multi-line headers from msnd example
        provided in issue #598

        This text contains headers like 'Case...', 'Doc...Filed...',
        'Main Document', and 'Desc'. The function should recognize these
        as non-content lines and return True (needs OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.msnd.49844/gov.uscourts.msnd.49844.2.0_1.pdf
        """
        msnd_text = """
Case: 3:24-cv-00304-MPM-JMV Doc #: 1 Filed: 09/25/24 1 of 7 PageID #: 1
Case: 3:24-cv-00304-MPM-JMV Doc #: 1 Filed: 09/25/24 2 of 7 PageID #: 2
3:24-cv-304-MPM-JMV
"""
        self.assertTrue(
            needs_ocr(msnd_text), msg="msnd example should need OCR"
        )

    def test_needs_ocr_wvnd_example(self):
        """Test needs_ocr with specific case number format from wvnd example.

        This text contains a case number line ('1:16-CV-107') and a
        'Received:' line. The function should recognize these as
        non-content lines and return True (needs OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.wvnd.38975/gov.uscourts.wvnd.38975.1.3_1.pdf
        """
        wvnd_text = """ 1:16-CV-107 Received: 06/03/2016 """
        self.assertTrue(
            needs_ocr(wvnd_text), msg="wvnd example should need OCR"
        )

    def test_needs_ocr_with_good_content(self):
        """Test needs_ocr returns False when substantive content is present.

        This text includes standard headers but also lines like
        'This is the first line of actual content.', which should cause
        the function to return False (doesn't need OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.flnd.526212/gov.uscourts.flnd.526212.13.0.pdf
        """
        good_text = """
Case 3:24-cv-00304-MCR-ZCB Document 13 Filed 01/27/25 Page 1 of 2

This is the first line of actual content.
Here is another line.
Here is another line.

Case 3:24-cv-00304-MCR-ZCB Document 13 Filed 01/27/25 Page 2 of 2
Some more content here.
Some more content here.
Some more content here.
"""
        self.assertFalse(
            needs_ocr(good_text), msg="Should not need OCR with good content"
        )

    def test_needs_ocr_only_standard_headers(self):
        """Test needs_ocr returns True for text with only basic headers/pagination.

        This tests the original scenario where only 'Case...' lines and
        'Page X of Y' lines are present. Should return True (needs OCR).

        Example: https://storage.courtlistener.com/recap/gov.uscourts.mdb.775852/gov.uscourts.mdb.775852..0.pdf
        """
        header_text = """
Case 23-15304   Doc   Filed 07/25/24   Page 1 of 8
Case 23-15304   Doc   Filed 07/25/24   Page 2 of 8
 0123ÿ567ÿ5859
Case 23-15304   Doc   Filed 07/25/24   Page 4 of 8
Case 23-15304   Doc   Filed 07/25/24   Page 5 of 8
"""
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_page_of_no_content(self):
        """Test needs_ocr returns True for pages with no content.

        This tests the original scenario where only 'Case...' lines and
        'Page X of Y' lines are present and no good content between pages lines.
        Should return True (needs OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.cacb.1850012/gov.uscourts.cacb.1850012..0.pdf
        """
        header_text = """
Case 8:19-bk-10049-TA   Doc    Filed 04/03/24 Entered 04/03/24 10:58:09   Desc Main
                              Document      Page 1 of 9
Case 8:19-bk-10049-TA   Doc    Filed 04/03/24 Entered 04/03/24 10:58:09   Desc Main
                              Document      Page 2 of 9
Case 8:19-bk-10049-TA   Doc    Filed 04/03/24 Entered 04/03/24 10:58:09   Desc Main
                              Document      Page 3 of 9

                                 April 3, 2024

                                             Person Name
Case 8:19-bk-10049-TA   Doc    Filed 04/03/24 Entered 04/03/24 10:58:09   Desc Main
                              Document      Page 4 of 9
"""
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_pg_of_no_content(self):
        """Test needs_ocr returns True for pages with no content.

        This tests the original scenario where only 'Case...' lines and
        'Pg X of Y' lines are present and no good content between pages lines.
        Should return True (needs OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.nysb.312902/gov.uscourts.nysb.312902.78.3.pdf
        """
        header_text = """
22-10964-mg   Doc 78-3   Filed 07/21/22 Entered 07/21/22 09:17:08   Attachment 3
                                     Pg 1 of 2
                                     Bad line 1
                                     Bad line 2
22-10964-mg   Doc 78-3   Filed 07/21/22 Entered 07/21/22 09:17:08   Attachment 3
                                     Pg 2 of 2
                                     Bad line 1
                                     Bad line 2
"""
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_good_content_page_colon(self):
        """Test needs_ocr returns False for pages with good content.

        This tests the original scenario where only 'Case...' lines and
        'Page:Y' lines are present and good content between pages lines is present.
        Should return False (doesn't need OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.ca1.08-9007.00105928542.0.pdf
        """
        header_text = """
Case: 08-9007   Document: 00115928542   Page: 1   Date Filed: 07/30/2009   Entry ID: 5364336
Line 1
Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
Line 3
Case: 08-9007   Document: 00115928542   Page: 2   Date Filed: 07/30/2009   Entry ID: 5364336
Line 1
Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
Line 3
Case: 08-9007   Document: 00115928542   Page: 3   Date Filed: 07/30/2009   Entry ID: 5364336
Line 1
Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
Line 3
"""
        self.assertFalse(
            needs_ocr(header_text),
            msg="Should not need OCR with good content",
        )

    def test_needs_ocr_under_threshold_page_colon(self):
        """Test the original scenario where only 'Case...' lines and
        'Page: Y' lines are present and good content between pages lines is
        present. Should return True (needs OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.ca1.08-9007.00105928542.0.pdf
        """
        header_text = """
Case: 08-9007   Document: 00115928542   Page: 1   Date Filed: 07/30/2009   Entry ID: 5364336
Line 1
Line 2
Case: 08-9007   Document: 00115928542   Page: 2   Date Filed: 07/30/2009   Entry ID: 5364336
Case: 08-9007   Document: 00115928542   Page: 3   Date Filed: 07/30/2009   Entry ID: 5364336
"""
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_empty_string(self):
        """Test needs_ocr returns True when the input content is an empty string."""
        self.assertTrue(needs_ocr(""), msg="Empty content should need OCR")

    def test_needs_ocr_only_whitespace(self):
        """Test needs_ocr returns True for content containing only whitespace.

        The function should strip lines, so whitespace-only lines are treated
        as empty, resulting in True (needs OCR).
        """
        self.assertTrue(
            needs_ocr("  \n\t\n  "),
            msg="Whitespace-only content should need OCR",
        )

    def test_needs_ocr_small_text_no_header(self):
        """Test needs_ocr function when the document has minimal text and no
        meaningful headers.

        When the average number of characters per page
        is below CHARS_THRESHOLD_OCR_PER_PAGE, the function should return True,
        indicating that OCR may be required.

        Example: https://storage.courtlistener.com/recap/gov.uscourts.ca1.51598/gov.uscourts.ca1.51598.108160115.0.pdf
        """
        text = """
        Missing Case Number:
         24-1442
        """
        self.assertTrue(
            needs_ocr(text, page_count=1),
            msg="small text example should need OCR",
        )

    def test_needs_ocr_pg_of_new_line_no_content(self):
        """Test needs_ocr returns True for pages with no content.

        This tests the original scenario where only 'Case...' lines and
        'Pg X of Y' lines are present and no good content between pages lines.
        Should return True (needs OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.nysb.312902/gov.uscourts.nysb.312902.78.3.pdf
        """
        header_text = """
Case No. 1:22-cv-00369-NYW-TPO   Document 1   filed 02/09/22   USDC Colorado   pg
                                    1 of 31
Case No. 1:22-cv-00369-NYW-TPO   Document 1   filed 02/09/22   USDC Colorado   pg
                                    2 of 31
Case No. 1:22-cv-00369-NYW-TPO   Document 1   filed 02/09/22   USDC Colorado   pg
                                    3 of 31
    """
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_caeb(self):
        """Test needs_ocr function with multi-line headers from caeb
        Example: https://storage.courtlistener.com/recap/gov.uscourts.caeb.656273/gov.uscourts.caeb.656273.19.0.pdf
        """

        # Date includes year with 4 digits.
        caeb_text = """
    Filed 11/02/21   Case 21-23295                Doc 19

                                 12/15/2021
Filed 11/02/21   Case 21-23295   Doc 19
Filed 11/02/21   Case 21-23295   Doc 19
        """

        # Date includes year with 2 digits.
        self.assertTrue(
            needs_ocr(caeb_text),
            msg="Should need OCR with only headers/pagination",
        )

        caeb_text = """
            Filed 11/02/21   Case 21-23295                Doc 19

                                         12/15/21
        Filed 11/02/21   Case 21-23295   Doc 19
        Filed 11/02/21   Case 21-23295   Doc 19
                """

        self.assertTrue(
            needs_ocr(caeb_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_pawd(self):
        """Test needs_ocr function with multi-line headers from pawd

        In this case, the content belongs to a seal whose character count is
        below CHARS_THRESHOLD_OCR_PER_PAGE.

        Example: https://storage.courtlistener.com/recap/gov.uscourts.pawb.358488/gov.uscourts.pawb.358488.28.0.pdf
        """

        caeb_text = """
        Case 18-24646-CMB   Doc 28   Filed 06/13/19 Entered 06/13/19 15:56:16   Desc Main
                                 Document     Page 1 of 1

        FILED
        6/13/19 3:55 pm
        CLERK
        U.S. BANKRUPTCY
        COURT - WDPA
            """

        self.assertTrue(
            needs_ocr(caeb_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_pg_number_line_no_content(self):
        """Test needs_ocr returns True for pages with no content.

        This tests the original scenario where only 'Case...' lines and
        'Pg X of Y' lines are present and no good content between pages lines.
        Should return True (needs OCR).
        Example: https://storage.courtlistener.com/recap/gov.uscourts.cod.243547/gov.uscourts.cod.243547.1.0.pdf
        """
        header_text = """
Case No. 1:25-cv-01340-RTG   Document 1 filed 04/29/25   USDC Colorado   pg 1
                                   of 20
Case No. 1:25-cv-01340-RTG   Document 1 filed 04/29/25   USDC Colorado   pg 2
                                   of 20
Case No. 1:25-cv-01340-RTG   Document 1 filed 04/29/25   USDC Colorado   pg 3
                                   of 20
    """
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_exhibit_exception(self):
        """Test needs_ocr returns False for pages with good content.

        Exception: if the first page contains the word "Exhibit", we assume
        it may be a valid exhibit cover page with little text, so we
        do not flag it for OCR.
        """
        header_text = """
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 1 of 7
                     Exhibit
                       A
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 2 of 7
        Good content 1
        Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
        Line 3
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 3 of 7
        Good content 1
        Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
        Line 3
            """
        self.assertFalse(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )

    def test_needs_ocr_exhibit_exception_true(self):
        """Test that needs_ocr returns True for pages that require OCR.

        Exception: If the first page contains the word "Exhibit," we assume
        it may be a valid exhibit cover page with little text, so we
        do not flag it for OCR. However, subsequent pages that match
        the criteria should still be flagged.
        """
        header_text = """
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 1 of 7
                     Exhibit
                       A
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 2 of 7
        Line 3
        Case 1:25-cv-02000   Document 1-1   Filed 06/26/25   Page 3 of 7
        Good content 1
        Pursuant to Rule 26.1 of the Fed. R. App. P. amici curiae herein state
        Line 3
            """
        self.assertTrue(
            needs_ocr(header_text),
            msg="Should need OCR with only headers/pagination",
        )


class TestS3CacheHelpers(TestCase):
    """Tests for the S3 cache helper functions in cl/lib/s3_cache.py"""

    @override_settings(DEVELOPMENT=True, TESTING=False)
    def test_get_s3_cache_returns_fallback_in_development(self) -> None:
        """In development mode, get_s3_cache should return the fallback cache."""
        cache = get_s3_cache("db_cache")
        # In development, should return db_cache, not s3
        # We verify by checking the cache backend class name
        self.assertIn("DatabaseCache", cache.__class__.__name__)

    @override_settings(DEVELOPMENT=False, TESTING=True)
    def test_get_s3_cache_returns_fallback_in_testing(self) -> None:
        """In testing mode, get_s3_cache should return the fallback cache."""
        cache = get_s3_cache("db_cache")
        self.assertIn("DatabaseCache", cache.__class__.__name__)

    @override_settings(DEVELOPMENT=False, TESTING=False)
    def test_get_s3_cache_returns_s3_in_production(self) -> None:
        """In production mode, get_s3_cache should return the S3 cache."""
        mock_s3_cache = MagicMock()
        mock_caches = {"s3": mock_s3_cache, "db_cache": MagicMock()}

        with patch("cl.lib.s3_cache.caches", mock_caches):
            with patch("cl.lib.s3_cache.switch_is_active", return_value=True):
                cache = get_s3_cache("db_cache")
                self.assertEqual(cache, mock_s3_cache)

    @override_settings(DEVELOPMENT=True, TESTING=False)
    def test_make_s3_cache_key_no_prefix_in_development(self) -> None:
        """In development mode, cache key should not have time-based prefix."""
        base_key = "clusters-mlt-es:123"
        timeout = 60 * 60 * 24 * 7  # 7 days

        result = make_s3_cache_key(base_key, timeout)
        self.assertEqual(result, base_key)

    @override_settings(DEVELOPMENT=False, TESTING=True)
    def test_make_s3_cache_key_no_prefix_in_testing(self) -> None:
        """In testing mode, cache key should not have time-based prefix."""
        base_key = "clusters-mlt-es:123"
        timeout = 60 * 60 * 24 * 7  # 7 days

        result = make_s3_cache_key(base_key, timeout)
        self.assertEqual(result, base_key)

    @override_settings(DEVELOPMENT=False, TESTING=False)
    def test_make_s3_cache_key_adds_prefix_in_production(self) -> None:
        """In production mode, cache key should have time-based prefix."""
        base_key = "clusters-mlt-es:123"
        timeout = 60 * 60 * 24 * 7  # 7 days

        with patch("cl.lib.s3_cache.switch_is_active", return_value=True):
            result = make_s3_cache_key(base_key, timeout)
            self.assertEqual(result, f"7-days:{base_key}")

    @override_settings(DEVELOPMENT=False, TESTING=False)
    def test_make_s3_cache_key_rounds_up_days(self) -> None:
        """Days calculation should round up (e.g., 1.5 days -> 2 days)."""
        base_key = "test-key"

        with patch("cl.lib.s3_cache.switch_is_active", return_value=True):
            # 1 day exactly
            self.assertEqual(
                make_s3_cache_key(base_key, 60 * 60 * 24), "1-days:test-key"
            )

            # 1.5 days -> rounds to 2
            self.assertEqual(
                make_s3_cache_key(base_key, 60 * 60 * 36), "2-days:test-key"
            )

            # 6 hours -> rounds to 1
            self.assertEqual(
                make_s3_cache_key(base_key, 60 * 60 * 6), "1-days:test-key"
            )

    @override_settings(DEVELOPMENT=False, TESTING=False)
    def test_make_s3_cache_key_persistent_in_production(self) -> None:
        """In production, timeout=None should use persistent prefix."""
        base_key = "clusters-mlt-es:123"
        with patch("cl.lib.s3_cache.switch_is_active", return_value=True):
            result = make_s3_cache_key(base_key, None)
            self.assertEqual(result, f"persistent:{base_key}")

    @override_settings(DEVELOPMENT=True, TESTING=False)
    def test_make_s3_cache_key_persistent_no_prefix_in_dev(self) -> None:
        """In dev/test, timeout=None should return key unchanged."""
        base_key = "clusters-mlt-es:123"
        result = make_s3_cache_key(base_key, None)
        self.assertEqual(result, base_key)


class TieredCacheTest(SimpleTestCase):
    """Tests for the tiered_cache decorator."""

    def setUp(self) -> None:
        clear_tiered_cache()
        self.call_count = 0

    def tearDown(self) -> None:
        clear_tiered_cache()

    def test_caches_result(self) -> None:
        """Test that tiered_cache caches the result of a function."""

        @tiered_cache(timeout=60)
        def expensive_function(x: int) -> int:
            self.call_count += 1
            return x * 2

        # First call should execute the function
        result1 = expensive_function(5)
        self.assertEqual(result1, 10)
        self.assertEqual(self.call_count, 1)

        # Second call should return cached result
        result2 = expensive_function(5)
        self.assertEqual(result2, 10)
        self.assertEqual(self.call_count, 1)  # Still 1, not called again

    def test_different_args_produce_different_cache_keys(self) -> None:
        """Test that different arguments produce different cache entries."""

        @tiered_cache(timeout=60)
        def multiply(x: int, y: int) -> int:
            self.call_count += 1
            return x * y

        # First call with (2, 3)
        result1 = multiply(2, 3)
        self.assertEqual(result1, 6)
        self.assertEqual(self.call_count, 1)

        # Call with different args (3, 4)
        result2 = multiply(3, 4)
        self.assertEqual(result2, 12)
        self.assertEqual(self.call_count, 2)

        # Call again with (2, 3) - should be cached
        result3 = multiply(2, 3)
        self.assertEqual(result3, 6)
        self.assertEqual(self.call_count, 2)

    def test_memory_cache_is_checked_before_redis(self) -> None:
        """Test that memory cache is checked before Redis cache."""

        @tiered_cache(timeout=60)
        def get_value() -> str:
            self.call_count += 1
            return "value"

        # First call populates both caches
        result1 = get_value()
        self.assertEqual(result1, "value")
        self.assertEqual(self.call_count, 1)

        # Clear Redis cache but leave memory cache (clear only tiered: keys)
        r = get_redis_interface("CACHE")
        keys = list(r.scan_iter(match=":1:tiered:*"))
        if keys:
            r.delete(*keys)

        # Second call should still return cached result from memory
        result2 = get_value()
        self.assertEqual(result2, "value")
        self.assertEqual(self.call_count, 1)

    def test_redis_cache_populates_memory_cache(self) -> None:
        """Test that reading from Redis cache also populates memory cache."""

        @tiered_cache(timeout=60)
        def get_data() -> dict:
            self.call_count += 1
            return {"key": "value"}

        # First call
        result1 = get_data()
        self.assertEqual(result1, {"key": "value"})
        self.assertEqual(self.call_count, 1)

        # Clear only memory cache, leave Redis cache intact
        _memory_cache.clear()

        # Second call should read from Redis and repopulate memory
        result2 = get_data()
        self.assertEqual(result2, {"key": "value"})
        self.assertEqual(self.call_count, 1)  # Still 1, read from Redis

    def test_kwargs_affect_cache_key(self) -> None:
        """Test that keyword arguments are included in cache key."""

        @tiered_cache(timeout=60)
        def greet(name: str, greeting: str = "Hello") -> str:
            self.call_count += 1
            return f"{greeting}, {name}!"

        result1 = greet("Alice", greeting="Hello")
        self.assertEqual(result1, "Hello, Alice!")
        self.assertEqual(self.call_count, 1)

        result2 = greet("Alice", greeting="Hi")
        self.assertEqual(result2, "Hi, Alice!")
        self.assertEqual(self.call_count, 2)

        result3 = greet("Alice", greeting="Hello")
        self.assertEqual(result3, "Hello, Alice!")
        self.assertEqual(self.call_count, 2)  # Cached
