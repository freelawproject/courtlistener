import datetime
from typing import Tuple, TypedDict, cast

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.db.models import F
from django.test import override_settings
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.mime_types import lookup_mime_type
from cl.lib.model_helpers import (
    clean_docket_number,
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
from cl.lib.privacy_tools import anonymize
from cl.lib.ratelimiter import parse_rate
from cl.lib.search_utils import make_fq
from cl.lib.string_utils import normalize_dashes, trunc
from cl.people_db.models import Role
from cl.recap.models import UPLOAD_TYPE, PacerHtmlFiles
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactoryMultipleOpinions,
)
from cl.search.models import Court, Docket, Opinion, OpinionCluster
from cl.tests.cases import SimpleTestCase, TestCase
from cl.users.factories import UserProfileWithParentsFactory


class TestPacerUtils(TestCase):
    fixtures = ["court_data.json"]

    def test_auto_blocking_small_bankr_docket(self) -> None:
        """Do we properly set small bankruptcy dockets to private?"""
        d = Docket()
        d.court = Court.objects.get(pk="akb")
        blocked, date_blocked = get_blocked_status(d)
        self.assertTrue(
            blocked,
            msg="Bankruptcy dockets with few entries should be blocked.",
        )
        blocked, date_blocked = get_blocked_status(d, count_override=501)
        self.assertFalse(
            blocked,
            msg="Bankruptcy dockets with many entries "
            "should not be blocked",
        )
        # This should stay blocked even though it's a big bankruptcy docket.
        d.blocked = True
        blocked, date_blocked = get_blocked_status(d, count_override=501)
        self.assertTrue(
            blocked,
            msg="Bankruptcy dockets that start blocked "
            "should stay blocked.",
        )


class TestStringUtils(SimpleTestCase):
    def test_trunc(self) -> None:
        """Does trunc give us the results we expect?"""

        class TestType(TypedDict, total=False):
            length: int
            result: str
            ellipsis: str

        s = "Henry wants apple."
        tests: Tuple[TestType, ...] = (
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
                msg="Failed with dict: %s.\n"
                "%s != %s" % (test_dict, result, test_dict["result"]),
            )
            self.assertTrue(
                len(result) <= test_dict["length"],
                msg="Failed with dict: %s.\n"
                "%s is longer than %s"
                % (test_dict, result, test_dict["length"]),
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


class TestMakeFQ(SimpleTestCase):
    def test_make_fq(self) -> None:
        test_pairs = (
            ("1 2", "1 AND 2"),
            ("1 and 2", "1 AND 2"),
            ('"1 AND 2"', '"1 AND 2"'),
            ('"1 2"', '"1 2"'),
            ("1 OR 2", "1 OR 2"),
            ("1 NOT 2", "1 NOT 2"),
            ("cause:sympathy", "cause AND sympathy"),
        )
        for test in test_pairs:
            field = "f"
            key = "key"
            self.assertEqual(
                make_fq(cd={key: test[0]}, field=field, key=key),
                f"{field}:({test[1]})",
            )


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


@override_settings(MAINTENANCE_MODE_ENABLED=True)
class TestMaintenanceMiddleware(TestCase):
    """Test the maintenance middleware"""

    @classmethod
    def setUpTestData(cls) -> None:
        # Do this in two steps to avoid triggering profile creation signal
        admin = UserProfileWithParentsFactory.create(
            user__username="admin",
            user__password=make_password("password"),
        )
        admin.user.is_superuser = True
        admin.user.is_staff = True
        admin.user.save()

    def test_middleware_works_when_enabled(self) -> None:
        """Does the middleware block users when enabled?"""
        r = self.client.get(reverse("show_results"))
        self.assertEqual(
            r.status_code,
            HTTP_503_SERVICE_UNAVAILABLE,
            "Did not get correct status code. Got: %s instead of %s"
            % (r.status_code, HTTP_503_SERVICE_UNAVAILABLE),
        )

    def test_staff_can_get_through(self) -> None:
        """Can staff get through when the middleware is enabled?"""
        self.assertTrue(
            self.client.login(username="admin", password="password")
        )
        r = self.client.get(reverse("show_results"))
        self.assertEqual(
            r.status_code,
            HTTP_200_OK,
            "Staff did not get through, but should have. Staff got status "
            "code of: %s instead of %s" % (r.status_code, HTTP_200_OK),
        )


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
        cluster_1 = OpinionClusterFactoryMultipleOpinions(
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
        cluster_2 = OpinionClusterFactoryMultipleOpinions(
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
