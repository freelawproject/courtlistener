import json
import os
from datetime import date, datetime
from glob import iglob
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings

from cl.corpus_importer.court_regexes import match_court_string
from cl.corpus_importer.import_columbia.parse_opinions import (
    get_state_court_object,
)
from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_body_content,
    compare_documents,
    parse_harvard_opinions,
    validate_dt,
)
from cl.corpus_importer.tasks import generate_ia_json
from cl.corpus_importer.utils import get_start_of_quarter
from cl.lib.pacer import process_docket_data
from cl.lib.storage import clobbering_get_name
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.mergers import find_docket_object
from cl.recap.models import UPLOAD_TYPE
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import (
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    RECAPDocument,
)
from cl.tests.cases import SimpleTestCase, TestCase


class JudgeExtractionTest(SimpleTestCase):
    def test_get_judge_from_string_columbia(self) -> None:
        """Can we cleanly get a judge value from a string?"""
        tests = (
            (
                "CLAYTON <italic>Ch. Jus. of the Superior Court,</italic> "
                "delivered the following opinion of this Court: ",
                ["clayton"],
            ),
            ("OVERTON, J. &#8212; ", ["overton"]),
            ("BURWELL, J.:", ["burwell"]),
        )
        for q, a in tests:
            self.assertEqual(extract_judge_last_name(q), a)


class CourtMatchingTest(SimpleTestCase):
    """Tests related to converting court strings into court objects."""

    def test_get_court_object_from_string(self) -> None:
        """Can we get a court object from a string and filename combo?

        When importing the Columbia corpus, we use a combination of regexes and
        the file path to determine a match.
        """
        pairs = (
            {
                "args": (
                    "California Superior Court  "
                    "Appellate Division, Kern County.",
                    "california/supreme_court_opinions/documents/0dc538c63bd07a28.xml",
                    # noqa
                ),
                "answer": "calappdeptsuperct",
            },
            {
                "args": (
                    "California Superior Court  "
                    "Appellate Department, Sacramento.",
                    "california/supreme_court_opinions/documents/0dc538c63bd07a28.xml",
                    # noqa
                ),
                "answer": "calappdeptsuperct",
            },
            {
                "args": (
                    "Appellate Session of the Superior Court",
                    "connecticut/appellate_court_opinions/documents/0412a06c60a7c2a2.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Court of Errors and Appeals.",
                    "new_jersey/supreme_court_opinions/documents/0032e55e607f4525.xml",
                    # noqa
                ),
                "answer": "nj",
            },
            {
                "args": (
                    "Court of Chancery",
                    "new_jersey/supreme_court_opinions/documents/0032e55e607f4525.xml",
                    # noqa
                ),
                "answer": "njch",
            },
            {
                "args": (
                    "Workers' Compensation Commission",
                    "connecticut/workers_compensation_commission/documents/0902142af68ef9df.xml",
                    # noqa
                ),
                "answer": "connworkcompcom",
            },
            {
                "args": (
                    "Appellate Session of the Superior Court",
                    "connecticut/appellate_court_opinions/documents/00ea30ce0e26a5fd.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Superior Court  New Haven County",
                    "connecticut/superior_court_opinions/documents/0218655b78d2135b.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Superior Court, Hartford County",
                    "connecticut/superior_court_opinions/documents/0218655b78d2135b.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Compensation Review Board  "
                    "WORKERS' COMPENSATION COMMISSION",
                    "connecticut/workers_compensation_commission/documents/00397336451f6659.xml",
                    # noqa
                ),
                "answer": "connworkcompcom",
            },
            {
                "args": (
                    "Appellate Division Of The Circuit Court",
                    "connecticut/superior_court_opinions/documents/03dd9ec415bf5bf4.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Superior Court for Law and Equity",
                    "tennessee/court_opinions/documents/01236c757d1128fd.xml",
                ),
                "answer": "tennsuperct",
            },
            {
                "args": (
                    "Courts of General Sessions and Oyer and Terminer "
                    "of Delaware",
                    "delaware/court_opinions/documents/108da18f9278da90.xml",
                ),
                "answer": "delsuperct",
            },
            {
                "args": (
                    "Circuit Court of the United States of Delaware",
                    "delaware/court_opinions/documents/108da18f9278da90.xml",
                ),
                "answer": "circtdel",
            },
            {
                "args": (
                    "Circuit Court of Delaware",
                    "delaware/court_opinions/documents/108da18f9278da90.xml",
                ),
                "answer": "circtdel",
            },
            {
                "args": (
                    "Court of Quarter Sessions "
                    "Court of Delaware,  Kent County.",
                    "delaware/court_opinions/documents/f01f1724cc350bb9.xml",
                ),
                "answer": "delsuperct",
            },
            {
                "args": (
                    "District Court of Appeal.",
                    "florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "District Court of Appeal, Lakeland, Florida.",
                    "florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "District Court of Appeal Florida.",
                    "florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "District Court of Appeal, Florida.",
                    "florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "District Court of Appeal of Florida, Second District.",
                    "florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "District Court of Appeal of Florida, Second District.",
                    "/data/dumps/florida/court_opinions/documents/25ce1e2a128df7ff.xml",
                    # noqa
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "U.S. Circuit Court",
                    "north_carolina/court_opinions/documents/fa5b96d590ae8d48.xml",
                    # noqa
                ),
                "answer": "circtnc",
            },
            {
                "args": (
                    "United States Circuit Court,  Delaware District.",
                    "delaware/court_opinions/documents/6abba852db7c12a1.xml",
                ),
                "answer": "circtdel",
            },
            {
                "args": ("Court of Common Pleas  Hartford County", "asdf"),
                "answer": "connsuperct",
            },
        )
        for d in pairs:
            got = get_state_court_object(*d["args"])
            self.assertEqual(
                got,
                d["answer"],
                msg="\nDid not get court we expected: '%s'.\n"
                "               Instead we got: '%s'" % (d["answer"], got),
            )

    def test_get_fed_court_object_from_string(self) -> None:
        """Can we get the correct federal courts?"""

        pairs = (
            {"q": "Eastern District of New York", "a": "nyed"},
            {"q": "Northern District of New York", "a": "nynd"},
            {"q": "Southern District of New York", "a": "nysd"},
            # When we have unknown first word, we assume it's errant.
            {"q": "Nathan District of New York", "a": "nyd"},
            {"q": "Nate District of New York", "a": "nyd"},
            {"q": "Middle District of Pennsylvania", "a": "pamd"},
            {"q": "Middle Dist. of Pennsylvania", "a": "pamd"},
            {"q": "M.D. of Pennsylvania", "a": "pamd"},
        )
        for test in pairs:
            print(f"Testing: {test['q']}, expecting: {test['a']}")
            got = match_court_string(test["q"], federal_district=True)
            self.assertEqual(test["a"], got)

    def test_get_appellate_court_object_from_string(self) -> None:
        """Can we get the correct federal appellate courts?"""

        pairs = (
            {"q": "U. S. Court of Appeals for the Ninth Circuit", "a": "ca9"},
            {
                # FJC data does not appear to have a space between U. and S.
                "q": "U.S. Court of Appeals for the Ninth Circuit",
                "a": "ca9",
            },
            {"q": "U. S. Circuit Court for the Ninth Circuit", "a": "ca9"},
            {"q": "U.S. Circuit Court for the Ninth Circuit", "a": "ca9"},
        )
        for test in pairs:
            print(f"Testing: {test['q']}, expecting: {test['a']}")
            got = match_court_string(test["q"], federal_appeals=True)
            self.assertEqual(test["a"], got)


@pytest.mark.django_db
class PacerDocketParserTest(TestCase):
    """Can we parse RECAP dockets successfully?"""

    fixtures = ["court_test_asset.json"]

    NUM_PARTIES = 3
    NUM_PETRO_ATTYS = 6
    NUM_FLOYD_ROLES = 3
    NUM_DOCKET_ENTRIES = 123

    @classmethod
    def setUpTestData(cls) -> None:
        docket_number = "3:11-cv-00064"
        cls.docket = DocketFactory.create(
            source=Docket.RECAP,
            pacer_case_id="41664",
            docket_number=docket_number,
            court=Court.objects.get(id="akd"),
            filepath_local__from_path=str(
                settings.MEDIA_ROOT
                / "test"
                / "xml"
                / "gov.uscourts.akd.41664.docket.xml"
            ),
        )

    def setUp(self) -> None:
        process_docket_data(self.docket, UPLOAD_TYPE.IA_XML_FILE)

    def tearDown(self) -> None:
        Docket.objects.all().delete()
        Party.objects.all().delete()
        Attorney.objects.all().delete()
        AttorneyOrganization.objects.all().delete()

    def test_docket_entry_parsing(self) -> None:
        """Do we get the docket entries we expected?"""
        # Total count is good?
        all_rds = RECAPDocument.objects.all()
        self.assertEqual(self.NUM_DOCKET_ENTRIES, all_rds.count())

        # Main docs exist and look about right?
        rd = RECAPDocument.objects.get(pacer_doc_id="0230856334")
        desc = rd.docket_entry.description
        good_de_desc = all(
            [
                desc.startswith("COMPLAINT"),
                "Filing fee" in desc,
                desc.endswith("2011)"),
            ]
        )
        self.assertTrue(good_de_desc)

        # Attachments have good data?
        att_rd = RECAPDocument.objects.get(pacer_doc_id="02301132632")
        self.assertTrue(
            all(
                [
                    att_rd.description.startswith("Judgment"),
                    "redistributed" in att_rd.description,
                    att_rd.description.endswith("added"),
                ]
            ),
            f"Description didn't match. Got: {att_rd.description}",
        )
        self.assertEqual(att_rd.attachment_number, 1)
        self.assertEqual(att_rd.document_number, "116")
        self.assertEqual(att_rd.docket_entry.date_filed, date(2012, 12, 10))

        # Two documents under the docket entry?
        self.assertEqual(att_rd.docket_entry.recap_documents.all().count(), 2)

    def test_party_parsing(self) -> None:
        """Can we parse an XML docket and get good results in the DB"""
        self.assertEqual(self.docket.parties.all().count(), self.NUM_PARTIES)

        petro = self.docket.parties.get(name__contains="Petro")
        self.assertEqual(petro.party_types.all()[0].name, "Plaintiff")

        attorneys = petro.attorneys.all().distinct()
        self.assertEqual(attorneys.count(), self.NUM_PETRO_ATTYS)

        floyd = petro.attorneys.distinct().get(name__contains="Floyd")
        self.assertEqual(floyd.roles.all().count(), self.NUM_FLOYD_ROLES)
        self.assertEqual(floyd.name, "Floyd G. Short")
        self.assertEqual(floyd.email, "fshort@susmangodfrey.com")
        self.assertEqual(floyd.fax, "(206) 516-3883")
        self.assertEqual(floyd.phone, "(206) 373-7381")

        godfrey_llp = floyd.organizations.all()[0]
        self.assertEqual(godfrey_llp.name, "Susman Godfrey, LLP")
        self.assertEqual(godfrey_llp.address1, "1201 Third Ave.")
        self.assertEqual(godfrey_llp.address2, "Suite 3800")
        self.assertEqual(godfrey_llp.city, "Seattle")
        self.assertEqual(godfrey_llp.state, "WA")


class GetQuarterTest(SimpleTestCase):
    """Can we properly figure out when the quarter that we're currently in
    began?
    """

    def test_january(self) -> None:
        self.assertEqual(
            date(2018, 1, 1), get_start_of_quarter(date(2018, 1, 1))
        )
        self.assertEqual(
            date(2018, 1, 1), get_start_of_quarter(date(2018, 1, 10))
        )

    def test_december(self) -> None:
        self.assertEqual(
            date(2018, 10, 1), get_start_of_quarter(date(2018, 12, 1))
        )


@pytest.mark.django_db
class IAUploaderTest(TestCase):
    """Tests related to uploading docket content to the Internet Archive"""

    fixtures = [
        "test_objects_query_counts.json",
        "attorney_party_dup_roles.json",
    ]

    def test_correct_json_generated(self) -> None:
        """Do we generate the correct JSON for a handful of tricky dockets?

        The most important thing here is that we don't screw up how we handle
        m2m relationships, which have a tendency of being tricky.
        """
        d, j_str = generate_ia_json(1)
        j = json.loads(j_str)
        parties = j["parties"]
        first_party = parties[0]
        first_party_attorneys = first_party["attorneys"]
        expected_num_attorneys = 1
        actual_num_attorneys = len(first_party_attorneys)
        self.assertEqual(
            expected_num_attorneys,
            actual_num_attorneys,
            msg="Got wrong number of attorneys when making IA JSON. "
            "Got %s, expected %s: \n%s"
            % (
                actual_num_attorneys,
                expected_num_attorneys,
                first_party_attorneys,
            ),
        )

        first_attorney = first_party_attorneys[0]
        attorney_roles = first_attorney["roles"]
        expected_num_roles = 1
        actual_num_roles = len(attorney_roles)
        self.assertEqual(
            actual_num_roles,
            expected_num_roles,
            msg="Got wrong number of roles on attorneys when making IA JSON. "
            "Got %s, expected %s" % (actual_num_roles, expected_num_roles),
        )

    def test_num_queries_ok(self) -> None:
        """Have we regressed the number of queries it takes to make the JSON

        It's very easy to use the DRF in a way that generates a LOT of queries.
        Let's avoid that.
        """
        with self.assertNumQueries(11):
            generate_ia_json(1)

        with self.assertNumQueries(9):
            generate_ia_json(2)

        with self.assertNumQueries(5):
            generate_ia_json(3)


class HarvardTests(TestCase):
    """
    Testing for cl.corpus_importer.management.commands.harvard_opinions
    """

    fixtures = ["court_test_asset.json"]
    test_dir = os.path.join(
        settings.INSTALL_ROOT, "cl", "corpus_importer", "test_assets"
    )

    def tearDown(self) -> None:
        Docket.objects.all().delete()

    def assertSuccessfulParse(self, expected_count_diff):
        pre_install_count = OpinionCluster.objects.all().count()
        parse_harvard_opinions(
            {
                "reporter": None,
                "volumes": None,
                "page": None,
                "make_searchable": False,
                "court_id": None,
                "location": None,
            }
        )
        post_install_count = OpinionCluster.objects.all().count()
        self.assertEqual(
            expected_count_diff, post_install_count - pre_install_count
        )
        print(post_install_count - pre_install_count, "✓")

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[[os.path.join(test_dir, "mass_court_new.json")]],
    )
    def test_new_case(self, mock):
        """Simple case: Can we install a case from JSON?"""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=454, reporter="Mass.", page=101)

        # Test some opinion attributes
        ops = cite.cluster.sub_opinions.all()
        expected_opinion_count = 1
        self.assertEqual(ops.count(), expected_opinion_count)

        op = ops[0]
        expected_op_type = Opinion.LEAD
        self.assertEqual(op.type, expected_op_type)

        expected_author_str = "Cowin"
        self.assertEqual(op.author_str, expected_author_str)

        # Test some cluster attributes
        cluster = cite.cluster
        expected_judges = "Cowin"
        self.assertEqual(cluster.judges, expected_judges)

        expected_date_filed = date(2009, 6, 12)
        self.assertEqual(cluster.date_filed, expected_date_filed)

        expected_case_name_full = "Commonwealth v. Willie Furr"
        self.assertEqual(cluster.case_name_full, expected_case_name_full)

        expected_other_dates = "March 3, 2009."
        self.assertEqual(cluster.other_dates, expected_other_dates)

        # Test some docket attributes
        docket = cite.cluster.docket

        expected_docket_number = "Docket No. 105739"
        self.assertEqual(docket.docket_number, expected_docket_number)

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "tax_court_similar*"))],
    )
    def test_duplicate_cite_different_case(self, mock):
        """Will we add a case with the same citation but a different case
        name?
        """
        self.assertSuccessfulParse(1)

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "bta_*.json"))],
    )
    def test_real_bta_failure(self, mock):
        """Will we add a case with the same citation but a different case
        name?
        """
        self.assertSuccessfulParse(2)

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "syllabus*"))],
    )
    def test_syllabus_and_summary_wrapping(self, mock):
        """Did we properly parse three syllabi?"""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=4, reporter="Kan.", page=283)
        self.assertEqual(cite.cluster.syllabus.count("<p>"), 3)
        self.assertEqual(cite.cluster.summary.count("<p>"), 32)

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "syllabus*"))],
    )
    def test_attorney_extraction(self, mock):
        """Did we properly parse attorneys?"""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=4, reporter="Kan.", page=283)
        print(cite.cluster.attorneys)
        self.assertEqual(
            cite.cluster.attorneys,
            "M. V. Voss, for plaintiff in error., W. O. Webb, for defendant in error., Voss, for plaintiff in error,, Webb, for defendant in error,",
        )
        print("✓")

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "per_curiam*"))],
    )
    def test_per_curiam(self, mock):
        """Did we identify the per curiam case."""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=381, reporter="A.2d", page=3)
        ops = cite.cluster.sub_opinions.all()
        self.assertEqual(ops[0].author_str, "Per Curiam")
        self.assertTrue(ops[0].per_curiam)
        print("Success ✓")

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "joined_by*"))],
    )
    def test_authors(self, mock):
        """Did we find the authors and the list of judges."""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=551, reporter="U.S.", page=193)
        ops = cite.cluster.sub_opinions.all().order_by("author_str")

        self.assertEqual(ops[0].author_str, "Stevens")
        self.assertEqual(ops[1].author_str, "Thomas")

        self.assertEqual(
            cite.cluster.judges,
            "Auto, Breyer, Ginsbtjrg, Kennedy, Roberts, Scaua, Sotjter, Stevens, Thomas",
        )
        print("Success ✓")

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "joined_by*"))],
    )
    def test_xml_harvard_extraction(self, mock):
        """Did we successfully not remove page citations while
        processing other elements?"""
        self.assertSuccessfulParse(1)
        cite = Citation.objects.get(volume=551, reporter="U.S.", page=193)
        opinions = cite.cluster.sub_opinions.all().order_by("-pk")
        self.assertEqual(opinions[0].xml_harvard.count("</page-number>"), 2)
        print("Success ✓")

    @patch(
        "cl.corpus_importer.management.commands.harvard_opinions.filepath_list",
        side_effect=[iglob(os.path.join(test_dir, "no_author_tag*"))],
    )
    def test_missing_page_numbers(self, mock):
        """Can we parse a case without an author or author tag?"""
        self.assertSuccessfulParse(1)
        print("Success ✓")

    def test_partial_dates(self) -> None:
        """Can we validate partial dates?"""
        pairs = (
            {"q": "2019-01-01", "a": "2019-01-01"},
            {"q": "2019-01", "a": "2019-01-15"},
            {"q": "2019-05", "a": "2019-05-15"},
            {"q": "1870-05", "a": "1870-05-15"},
            {"q": "2019", "a": "2019-07-01"},
        )
        for test in pairs:
            print(f"Testing: {test['q']}, expecting: {test['a']}")
            got = validate_dt(test["q"])
            dt_obj = datetime.strptime(test["a"], "%Y-%m-%d").date()
            self.assertEqual(dt_obj, got[0])
            print("Success ✓")

    def test_short_opinion_matching(self) -> None:
        """Can we match opinions successfully when very small"""
        aspby_case_body = '<casebody firstpage="1007" lastpage="1007" xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1">\n  <parties id="b985-7">State, Respondent, v. Aspby, Petitioner,</parties>\n  <docketnumber id="Apx">No. 73722-3.</docketnumber>\n  <opinion type="majority">\n    <p id="AJ6">Petition for review of a decision of the Court of Appeals, No. 48369-2-1, September 19, 2002. <em>Denied </em>September 30, 2003.</p>\n  </opinion>\n</casebody>\n'

        matching_cl_case = "Petition for review of a decision of the Court of Appeals, No. 48369-2-1, September 19, 2002. Denied September 30, 2003."
        nonmatch_cl_case = "Petition for review of a decision of the Court of Appeals, No. 19667-4-III, October 31, 2002. Denied September 30, 2003."

        harvard_characters = clean_body_content(aspby_case_body)
        good_characters = clean_body_content(matching_cl_case)
        bad_characters = clean_body_content(nonmatch_cl_case)

        good_match = compare_documents(harvard_characters, good_characters)
        self.assertEqual(good_match, 100)

        bad_match = compare_documents(harvard_characters, bad_characters)
        self.assertEqual(bad_match, 81)
