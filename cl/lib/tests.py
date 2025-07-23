import datetime
import pickle
from typing import TypedDict, cast
from unittest import mock
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings
from requests.cookies import RequestsCookieJar

from cl.lib.courts import (
    get_active_court_from_cache,
    get_minimal_list_of_courts,
    lookup_child_courts_cache,
)
from cl.lib.date_time import midnight_pt
from cl.lib.elasticsearch_utils import append_query_conjunctions
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.mime_types import lookup_mime_type
from cl.lib.model_helpers import (
    clean_docket_number,
    is_docket_number,
    linkify_orig_docket_number,
    make_docket_number_core,
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
from cl.lib.redis_utils import (
    acquire_redis_lock,
    get_redis_interface,
    release_redis_lock,
)
from cl.lib.search_index_utils import get_parties_from_case_name_bankr
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
        session_data = get_or_cache_pacer_cookies(
            "test_user_new_cookie", username="test", password="password"
        )
        self.assertEqual(mock_log_into_pacer.call_count, 1)
        self.assertIsInstance(session_data, SessionData)
        self.assertEqual(session_data.proxy_address, "http://proxy_1:9090")

    @patch("cl.lib.pacer_session.log_into_pacer")
    def test_parse_cookie_proxy_pair_properly(self, mock_log_into_pacer):
        """Can we parse the dataclass from cache properly?"""
        session_data = get_or_cache_pacer_cookies(
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
        session_data = get_or_cache_pacer_cookies(
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

        # Not valid docket number formats for district, bankruptcy or appellate
        # not docket number returned
        self.assertEqual(clean_docket_number("Nos. C 123-80-123-82"), "")
        self.assertEqual(clean_docket_number("Nos. C 123-80-123"), "")
        self.assertEqual(clean_docket_number("Nos. 212-213"), "")

        # Multiple valid docket numbers, not docket number returned
        self.assertEqual(
            clean_docket_number("Nos. 14-13542, 14-13657, 15-10967, 15-11166"),
            "",
        )
        self.assertEqual(clean_docket_number("12-33112, 12-33112"), "")

        # One valid docket number, return the cleaned number
        self.assertEqual(
            clean_docket_number("CIVIL ACTION NO. 7:17-CV-00426"),
            "7:17-cv-00426",
        )
        self.assertEqual(
            clean_docket_number("Case No.1:19-CV-00118-MRB"), "1:19-cv-00118"
        )
        self.assertEqual(clean_docket_number("Case 12-33112"), "12-33112")
        self.assertEqual(clean_docket_number("12-33112"), "12-33112")
        self.assertEqual(
            clean_docket_number("12-cv-01032-JKG-MJL"), "12-cv-01032"
        )
        self.assertEqual(
            clean_docket_number("Nos. 212-213, Dockets 27264, 27265"), ""
        )
        self.assertEqual(
            clean_docket_number("Nos. 12-213, Dockets 27264, 27265"), "12-213"
        )

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
