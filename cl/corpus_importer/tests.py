import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from queue import Queue
from random import randint
from unittest.mock import patch

import eyecite
import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import make_aware
from factory import RelatedFactory
from juriscraper.lib.string_utils import harmonize

from cl.corpus_importer.court_regexes import match_court_string
from cl.corpus_importer.factories import (
    CaseBodyFactory,
    CaseLawCourtFactory,
    CaseLawFactory,
    CitationFactory,
    RssDocketDataFactory,
    RssDocketEntryDataFactory,
)
from cl.corpus_importer.import_columbia.parse_opinions import (
    get_state_court_object,
)
from cl.corpus_importer.management.commands.clean_up_mis_matched_dockets import (
    find_and_fix_mis_matched_dockets,
)
from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_body_content,
    compare_documents,
    parse_harvard_opinions,
    validate_dt,
    winnow_case_name,
)
from cl.corpus_importer.management.commands.normalize_judges_opinions import (
    Command,
    normalize_authors_in_opinions,
    normalize_panel_in_opinioncluster,
)
from cl.corpus_importer.management.commands.troller_bk import (
    download_files_concurrently,
    log_added_items_to_redis,
    merge_rss_data,
)
from cl.corpus_importer.tasks import generate_ia_json
from cl.corpus_importer.utils import get_start_of_quarter
from cl.lib.pacer import process_docket_data
from cl.lib.redis_utils import make_redis_interface
from cl.lib.timezone_helpers import localize_date_and_time
from cl.people_db.factories import PersonWithChildrenFactory, PositionFactory
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.models import UPLOAD_TYPE
from cl.recap_rss.models import RssItemCache
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionClusterWithParentsFactory,
    OpinionWithChildrenFactory,
    RECAPDocumentFactory,
)
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    RECAPDocument,
)
from cl.settings import MEDIA_ROOT
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
                    "california/supreme_court_opinions/documents"
                    "/0dc538c63bd07a28.xml",
                    # noqa
                ),
                "answer": "calappdeptsuperct",
            },
            {
                "args": (
                    "California Superior Court  "
                    "Appellate Department, Sacramento.",
                    "california/supreme_court_opinions/documents"
                    "/0dc538c63bd07a28.xml",
                    # noqa
                ),
                "answer": "calappdeptsuperct",
            },
            {
                "args": (
                    "Appellate Session of the Superior Court",
                    "connecticut/appellate_court_opinions/documents"
                    "/0412a06c60a7c2a2.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Court of Errors and Appeals.",
                    "new_jersey/supreme_court_opinions/documents"
                    "/0032e55e607f4525.xml",
                    # noqa
                ),
                "answer": "nj",
            },
            {
                "args": (
                    "Court of Chancery",
                    "new_jersey/supreme_court_opinions/documents"
                    "/0032e55e607f4525.xml",
                    # noqa
                ),
                "answer": "njch",
            },
            {
                "args": (
                    "Workers' Compensation Commission",
                    "connecticut/workers_compensation_commission/documents"
                    "/0902142af68ef9df.xml",
                    # noqa
                ),
                "answer": "connworkcompcom",
            },
            {
                "args": (
                    "Appellate Session of the Superior Court",
                    "connecticut/appellate_court_opinions/documents"
                    "/00ea30ce0e26a5fd.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Superior Court  New Haven County",
                    "connecticut/superior_court_opinions/documents"
                    "/0218655b78d2135b.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Superior Court, Hartford County",
                    "connecticut/superior_court_opinions/documents"
                    "/0218655b78d2135b.xml",
                    # noqa
                ),
                "answer": "connsuperct",
            },
            {
                "args": (
                    "Compensation Review Board  "
                    "WORKERS' COMPENSATION COMMISSION",
                    "connecticut/workers_compensation_commission/documents"
                    "/00397336451f6659.xml",
                    # noqa
                ),
                "answer": "connworkcompcom",
            },
            {
                "args": (
                    "Appellate Division Of The Circuit Court",
                    "connecticut/superior_court_opinions/documents"
                    "/03dd9ec415bf5bf4.xml",
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
                    "/data/dumps/florida/court_opinions/documents"
                    "/25ce1e2a128df7ff.xml",
                    # noqa
                ),
                "answer": "fladistctapp",
            },
            {
                "args": (
                    "U.S. Circuit Court",
                    "north_carolina/court_opinions/documents"
                    "/fa5b96d590ae8d48.xml",
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

    NUM_PARTIES = 3
    NUM_PETRO_ATTYS = 6
    NUM_FLOYD_ROLES = 3
    NUM_DOCKET_ENTRIES = 3

    @classmethod
    def setUpTestData(cls) -> None:
        cls.fp = (
            MEDIA_ROOT / "test" / "xml" / "gov.uscourts.akd.41664.docket.xml"
        )
        docket_number = "3:11-cv-00064"
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create(
            source=Docket.RECAP,
            pacer_case_id="41664",
            docket_number=docket_number,
            court=cls.court,
            filepath_local__from_path=str(cls.fp),
        )

    def setUp(self) -> None:
        process_docket_data(self.docket, UPLOAD_TYPE.IA_XML_FILE, self.fp)

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
    def setUp(self):
        """Setup harvard tests

        This setup is a little distinct from normal ones.  Here we are actually
        setting up our patches which are used by the majority of the tests.
        Each one can be used or turned off.  See the teardown for more.
        :return:
        """
        self.make_filepath_patch = patch(
            "cl.corpus_importer.management.commands.harvard_opinions.filepath_list"
        )
        self.filepath_list_func = self.make_filepath_patch.start()
        self.read_json_patch = patch(
            "cl.corpus_importer.management.commands.harvard_opinions.read_json"
        )
        self.read_json_func = self.read_json_patch.start()
        self.find_court_patch = patch(
            "cl.corpus_importer.management.commands.harvard_opinions.find_court"
        )
        self.find_court_func = self.find_court_patch.start()

        # Default values for Harvard Tests
        self.filepath_list_func.return_value = ["/one/fake/filepath.json"]
        self.find_court_func.return_value = ["harvard"]

    @classmethod
    def setUpTestData(cls) -> None:
        for court in ["harvard", "alnb"]:
            CourtFactory.create(id=court)

    def tearDown(self) -> None:
        """Tear down patches and remove added objects"""
        self.make_filepath_patch.stop()
        self.read_json_patch.stop()
        self.find_court_patch.stop()
        Docket.objects.all().delete()
        Court.objects.all().delete()

    def _get_cite(self, case_law) -> Citation:
        """Fetch first citation added to case

        :param case_law: Case object
        :return: First citation found
        """
        cites = eyecite.get_citations(case_law["citations"][0]["cite"])
        cite = Citation.objects.get(
            volume=cites[0].groups["volume"],
            reporter=cites[0].groups["reporter"],
            page=cites[0].groups["page"],
        )
        return cite

    def assertSuccessfulParse(self, expected_count_diff, bankruptcy=False):
        pre_install_count = OpinionCluster.objects.all().count()
        parse_harvard_opinions(
            {
                "reporter": None,
                "volumes": None,
                "page": None,
                "make_searchable": False,
                "court_id": None,
                "location": None,
                "bankruptcy": bankruptcy,
            }
        )
        post_install_count = OpinionCluster.objects.all().count()
        self.assertEqual(
            expected_count_diff, post_install_count - pre_install_count
        )
        print(post_install_count - pre_install_count, "✓")

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

    def test_short_opinion_matching(self) -> None:
        """Can we match opinions successfully when very small?"""
        aspby_case_body = '<casebody firstpage="1007" lastpage="1007" \
xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1">\n\
<parties id="b985-7">State, Respondent, v. Aspby, Petitioner,</parties>\n \
<docketnumber id="Apx">No. 73722-3.</docketnumber>\n  <opinion type="majority">\n \
<p id="AJ6">Petition for review of a decision of the Court of Appeals,\
 No. 48369-2-1, September 19, 2002. <em>Denied </em>September 30, 2003.\
</p>\n  </opinion>\n</casebody>\n'

        matching_cl_case = "Petition for review of a decision of the Court of \
Appeals, No. 48369-2-1, September 19, 2002. Denied September 30, 2003."
        nonmatch_cl_case = "Petition for review of a decision of the Court of \
Appeals, No. 19667-4-III, October 31, 2002. Denied September 30, 2003."

        harvard_characters = clean_body_content(aspby_case_body)
        good_characters = clean_body_content(matching_cl_case)
        bad_characters = clean_body_content(nonmatch_cl_case)

        good_match = compare_documents(harvard_characters, good_characters)
        self.assertEqual(good_match, 100)

        bad_match = compare_documents(harvard_characters, bad_characters)
        self.assertEqual(bad_match, 81)

    def test_new_case(self):
        """Can we import a new case?"""
        case_law = CaseLawFactory()
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)

        cite = self._get_cite(case_law)
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

        self.assertEqual(cluster.judges, expected_author_str)
        self.assertEqual(
            cluster.date_filed,
            datetime.strptime(case_law["decision_date"], "%Y-%m-%d").date(),
        )
        self.assertEqual(cluster.case_name_full, case_law["name"])

        expected_other_dates = "March 3, 2009."
        self.assertEqual(cluster.other_dates, expected_other_dates)

        # Test some docket attributes
        docket = cite.cluster.docket
        self.assertEqual(docket.docket_number, case_law["docket_number"])

    def test_existing_docket_lookup(self):
        """Can we update an existing docket instead of creating a new one?"""

        case_law = CaseLawFactory()
        DocketFactory(
            docket_number=case_law["docket_number"],
            court_id="harvard",
            source=Docket.HARVARD,
            pacer_case_id=None,
            idb_data=None,
        )

        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)

        cite = self._get_cite(case_law)

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 1)

        # Test some docket attributes
        docket = cite.cluster.docket
        self.assertEqual(docket.docket_number, case_law["docket_number"])
        self.assertEqual(
            docket.case_name, harmonize(case_law["name_abbreviation"])
        )
        self.assertEqual(docket.ia_needs_upload, False)

    def test_new_bankruptcy_case(self):
        """Can we add a bankruptcy court?"""

        # Disable court_func patch to test ability to identify bank. ct.
        self.find_court_patch.stop()

        self.read_json_func.return_value = CaseLawFactory(
            court=CaseLawCourtFactory.create(
                name="United States Bankruptcy Court for the Northern "
                "District of Alabama "
            )
        )
        self.assertSuccessfulParse(0)
        self.assertSuccessfulParse(1, bankruptcy=True)

    def test_syllabus_and_summary_wrapping(self):
        """Did we properly parse syllabus and summary?"""
        data = '<casebody>  <summary id="b283-8"><em>Error from Bourbon \
Bounty.</em></summary>\
<syllabus id="b283-9">Confessions of judgment, provided for in title 11,\
 chap. 3, civil code, must be made in open court; a judgment entered on a \
confession taken by the clerk in vacation, is a nullity. <em>Semble, </em>the \
clerk, in vacation, is only authorized by § 389 to enter in vacation a judgment \
rendered by the court.</syllabus> <opinion type="majority"><p id="AvW"> \
delivered the opinion of the Court.</p></opinion> </casebody>'

        self.read_json_func.return_value = CaseLawFactory.create(
            casebody=CaseBodyFactory.create(data=data),
        )
        self.assertSuccessfulParse(1)
        cite = self._get_cite(self.read_json_func.return_value)
        self.assertEqual(cite.cluster.syllabus.count("<p>"), 1)
        self.assertEqual(cite.cluster.summary.count("<p>"), 1)

    def test_attorney_extraction(self):
        """Did we properly parse attorneys?"""
        data = '<casebody> <attorneys id="b284-5"><em>M. V. Voss, \
</em>for plaintiff in error.</attorneys> <attorneys id="b284-6">\
<em>W. O. Webb, </em>for defendant in error.</attorneys> \
<attorneys id="b284-7"><em>Voss, </em>for plaintiff in error,\
</attorneys> <attorneys id="b289-5"><em>Webb, </em>\
<page-number citation-index="1" label="294">*294</page-number>for \
defendant in error,</attorneys> <opinion type="majority"><p id="AvW"> \
delivered the opinion of the Court.</p></opinion> </casebody>'
        case_law = CaseLawFactory.create(
            casebody=CaseBodyFactory.create(data=data)
        )
        self.read_json_func.return_value = case_law

        self.assertSuccessfulParse(1)
        cite = self._get_cite(case_law)
        self.assertEqual(
            cite.cluster.attorneys,
            "M. V. Voss, for plaintiff in error., W. O. Webb, for defendant "
            "in error., Voss, for plaintiff in error,, Webb, for defendant "
            "in error,",
        )

    def test_per_curiam(self):
        """Did we identify the per curiam case."""
        case_law = CaseLawFactory.create(
            casebody=CaseBodyFactory.create(
                data='<casebody><opinion type="majority"><author '
                'id="b56-3">PER CURIAM:</author></casebody> '
            ),
        )
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)
        cite = self._get_cite(case_law)

        ops = cite.cluster.sub_opinions.all()
        self.assertEqual(ops[0].author_str, "Per Curiam")
        self.assertTrue(ops[0].per_curiam)

    def test_authors(self):
        """Did we find the authors and the list of judges."""
        casebody = """<casebody>
  <judges id="b246-5">Thomas, J., delivered the opinion of the \
  Court, in which Roberts, C. J., and Scaua, <page-number citation-index="1" \
  label="194">Kennedy, Sotjter, Ginsbtjrg, and Auto, JJ., joined. Stevens, J., \
   filed a dissenting opinion, in which Breyer, J., joined, \
   <em>post, </em>p. 202.</judges>
  <opinion type="majority">
    <author id="b247-5">Justice Thomas</author>
    <p id="AvW">delivered the opinion of the Court.</p>
  </opinion>
  <opinion type="dissent">
    <author id="b254-6">Justice Stevens,</author>
    <p id="Ab5">with whom Justice Breyer joins, dissenting.</p>
  </opinion>
</casebody>
        """
        case_law = CaseLawFactory(
            casebody=CaseBodyFactory.create(data=casebody),
        )
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)

        cite = self._get_cite(case_law)
        ops = cite.cluster.sub_opinions.all().order_by("author_str")

        self.assertEqual(ops[0].author_str, "Stevens")
        self.assertEqual(ops[1].author_str, "Thomas")

        self.assertEqual(
            cite.cluster.judges,
            "Auto, Breyer, Ginsbtjrg, Kennedy, Roberts, Scaua, Sotjter, "
            "Stevens, Thomas",
        )

    def test_xml_harvard_extraction(self):
        """Did we successfully not remove page citations while
        processing other elements?"""
        data = """
<casebody firstpage="1" lastpage="2">
<opinion type="majority">Everybody <page-number citation-index="1" \
label="194">*194</page-number>
 and next page <page-number citation-index="1" label="195">*195
 </page-number>wins.
 </opinion>
 </casebody>
"""
        case_law = CaseLawFactory.create(
            casebody=CaseBodyFactory.create(data=data),
        )
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)
        cite = self._get_cite(case_law)

        opinions = cite.cluster.sub_opinions.all().order_by("-pk")
        self.assertEqual(opinions[0].xml_harvard.count("</page-number>"), 2)

    def test_same_citation_different_case(self):
        """Same case name, different opinion - based on a BTA bug"""
        case_law = CaseLawFactory()
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)

        case_law["casebody"] = CaseBodyFactory.create(
            data='<casebody firstpage="1" lastpage="2">\n  \
            <opinion type="minority">Something else.</opinion>\n</casebody>'
        )
        self.read_json_func.return_value = case_law
        self.filepath_list_func.return_value = ["/another/fake/filepath.json"]
        self.assertSuccessfulParse(1)

    def test_bad_ibid_citation(self):
        """Can we add a case with a bad ibid citation?"""
        citations = [
            "7 Ct. Cl. 65",
            "1 Ct. Cls. R., p. 270, 3 id., p. 10; 7 W. R., p. 666",
        ]
        case_law = CaseLawFactory(
            citations=[CitationFactory(cite=cite) for cite in citations],
        )
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)
        cite = self._get_cite(case_law)
        self.assertEqual(str(cite), "7 Ct. Cl. 65")

    def test_no_volume_citation(self):
        """Can we handle an opinion that contains a citation without a
        volume?"""
        citations = [
            "Miller's Notebook, 179",
        ]
        case_law = CaseLawFactory(
            citations=[CitationFactory(cite=cite) for cite in citations],
        )
        self.read_json_func.return_value = case_law
        self.assertSuccessfulParse(1)

    def test_case_name_winnowing_comparison(self):
        """
        Test removing "United States" from case names and check if there is an
        overlap between two case names.
        """
        case_name_full = (
            "UNITED STATES of America, Plaintiff-Appellee, "
            "v. Wayne VINSON, Defendant-Appellant "
        )
        case_name_abbreviation = "United States v. Vinson"
        harvard_case = f"{case_name_full} {case_name_abbreviation}"

        case_name_cl = "United States v. Frank Esquivel"
        overlap = winnow_case_name(case_name_cl) & winnow_case_name(
            harvard_case
        )
        self.assertEqual(len(overlap), 0)

    def test_case_names_with_abbreviations(self):
        """
        Test what happens when the case name contains abbreviations
        """

        # Check against itself, there must be an overlap
        case_1_data = {
            "case_name_full": "In the matter of S.J.S., a minor child. "
            "D.L.M. and D.E.M., Petitioners/Respondents v."
            " T.J.S.",
            "case_name_abbreviation": "D.L.M. v. T.J.S.",
            "case_name_cl": "D.L.M. v. T.J.S.",
            "overlaps": 2,
        }

        case_2_data = {
            "case_name_full": "Appeal of HAMILTON & CHAMBERS CO., INC.",
            "case_name_abbreviation": "Appeal of Hamilton & Chambers Co.",
            "case_name_cl": "Appeal of Hamilton & Chambers Co.",
            "overlaps": 4,
        }

        # Check against different case name, there shouldn't be an overlap
        case_3_data = {
            "case_name_full": "Henry B. Wesselman et al., as Executors of "
            "Blanche Wesselman, Deceased, Respondents, "
            "v. The Engel Company, Inc., et al., "
            "Appellants, et al., Defendants",
            "case_name_abbreviation": "Wesselman v. Engel Co.",
            "case_name_cl": " McQuillan v. Schechter",
            "overlaps": 0,
        }

        cases = [case_1_data, case_2_data, case_3_data]

        for case in cases:
            harvard_case = f"{case.get('case_name_full')} {case.get('case_name_abbreviation')}"
            overlap = winnow_case_name(
                case.get("case_name_cl")
            ) & winnow_case_name(harvard_case)

            self.assertEqual(len(overlap), case.get("overlaps"))


class CorpusImporterManagementCommmandsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="nyappdiv")

        # Create object person
        cls.judge = PersonWithChildrenFactory.create(
            name_first="Paul",
            name_middle="J.",
            name_last="Yesawich",
            name_suffix="jr",
            date_dob="1923-11-27",
            date_granularity_dob="%Y-%m-%d",
        )
        position = PositionFactory.create(court=cls.court, person=cls.judge)
        cls.judge.positions.add(position)

        cls.judge_2 = PersonWithChildrenFactory.create(
            name_first="Harold",
            name_middle="Fleming",
            name_last="Snead",
            name_suffix="jr",
            date_dob="1903-06-16",
            date_granularity_dob="%Y-%m-%d",
            date_dod="1987-12-23",
            date_granularity_dod="%Y-%m-%d",
        )
        position_2 = PositionFactory.create(
            court=cls.court, person=cls.judge_2
        )
        cls.judge_2.positions.add(position_2)

    def test_normalize_author_str(self):
        """Normalize author_str field in opinions in Person object"""

        # Create opinion cluster with opinion and docket
        cluster = (
            OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(
                    court=self.court,
                    case_name="Foo v. Bar",
                    case_name_full="Foo v. Bar",
                ),
                case_name="Foo v. Bar",
                date_filed=date.today(),
                sub_opinions=RelatedFactory(
                    OpinionWithChildrenFactory,
                    factory_related_name="cluster",
                    plain_text="Sample text",
                    author_str="Yesawich",
                    author=None,
                ),
            ),
        )

        # Check that the opinion doesn't have an author
        self.assertEqual(cluster[0].sub_opinions.all().first().author, None)

        # Run function to normalize authors in opinions
        normalize_authors_in_opinions()

        # Reload field values from the database.
        cluster[0].refresh_from_db()

        #  Check that the opinion now have an author
        self.assertEqual(
            cluster[0].sub_opinions.all().first().author, self.judge
        )

    def test_normalize_panel_str(self):
        """Normalize judges string field into panel field(m2m)"""

        cluster = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="Lorem v. Ipsum",
                case_name_full="Lorem v. Ipsum",
            ),
            case_name="Lorem v. Ipsum",
            date_filed=date.today(),
            judges="Snead, Yesawich",
        )

        # Check panel is empty
        self.assertEqual(len(cluster.panel.all()), 0)

        # Run function to normalize panel in opinion clusters
        normalize_panel_in_opinioncluster()

        # Reload field values from the database
        cluster.refresh_from_db()

        # Check that the opinion cluster now have judges in panel
        self.assertEqual(len(cluster.panel.all()), 2)


def mock_download_file(item_path, order):
    time.sleep(randint(1, 10) / 100)
    return b"", item_path, order


class TrollerBKTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # District factories
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_neb = CourtFactory(id="nebraskab", jurisdiction="FD")
        cls.court_pamd = CourtFactory(id="pamd", jurisdiction="FD")
        cls.docket_d_before_2018 = DocketFactory(
            case_name="Young v. State",
            docket_number="3:17-CV-01477",
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id="1234",
        )

        cls.docket_d_after_2018 = DocketFactory(
            case_name="Dragon v. State",
            docket_number="3:15-CV-01455",
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id="5431",
        )

        cls.de_d_before_2018 = DocketEntryWithParentsFactory(
            docket__court=cls.court,
            docket__case_name="Young Entry v. Dragon",
            docket__docket_number="3:87-CV-01400",
            docket__source=Docket.HARVARD,
            docket__pacer_case_id="9038",
            entry_number=1,
            date_filed=make_aware(
                datetime(year=2018, month=1, day=4), timezone.utc
            ),
        )

        # Appellate factories
        cls.court_appellate = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket_a_before_2018 = DocketFactory(
            case_name="Young v. State",
            docket_number="12-2532",
            court=cls.court_appellate,
            source=Docket.HARVARD,
            pacer_case_id=None,
        )
        cls.docket_a_after_2018 = DocketFactory(
            case_name="Dragon v. State",
            docket_number="15-1232",
            court=cls.court_appellate,
            source=Docket.HARVARD,
            pacer_case_id=None,
        )
        cls.de_a_before_2018 = DocketEntryWithParentsFactory(
            docket__court=cls.court_appellate,
            docket__case_name="Young Entry v. Dragon",
            docket__docket_number="12-3242",
            docket__source=Docket.HARVARD,
            docket__pacer_case_id=None,
            entry_number=1,
            date_filed=make_aware(
                datetime(year=2018, month=1, day=4), timezone.utc
            ),
        )
        cls.docket_a_2018_case_id = DocketFactory(
            case_name="Young v. State",
            docket_number="12-5674",
            court=cls.court_appellate,
            source=Docket.RECAP,
            pacer_case_id="12524",
        )

    def setUp(self) -> None:
        self.r = make_redis_interface("STATS")
        self.r.flushdb()

    def test_merge_district_rss_before_2018(self):
        """1 Test merge district RSS file before 2018-4-20 into an existing
        docket

        Before 2018-4-20
        District
        Docket exists
        No docket entries

        Merge docket entries, avoid updating metadata.
        """
        d_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Young v. Dragon",
            docket_number="3:17-CV-01473",
            pacer_case_id="1234",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.docket_d_before_2018.docket_entries.all()), 0
        )
        rds_created, d_created = merge_rss_data(
            [d_rss_data_before_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.docket_d_before_2018.refresh_from_db()
        self.assertEqual(self.docket_d_before_2018.case_name, "Young v. State")
        self.assertEqual(
            self.docket_d_before_2018.docket_number, "3:17-CV-01477"
        )
        self.assertEqual(
            len(self.docket_d_before_2018.docket_entries.all()), 1
        )
        self.assertEqual(
            self.docket_d_before_2018.source, Docket.HARVARD_AND_RECAP
        )

    def test_avoid_merging_district_rss_after_2018(self):
        """2 Test avoid merging district RSS file after 2018-4-20

        After 2018-4-20
        District
        Docket exists
        No docket entries

        Don't merge docket entries, avoid updating metadata.
        """
        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Dragon 1 v. State",
            docket_number="3:15-CV-01456",
            pacer_case_id="5431",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2018, month=4, day=21), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(len(self.docket_d_after_2018.docket_entries.all()), 0)
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)
        self.docket_d_after_2018.refresh_from_db()
        self.assertEqual(self.docket_d_after_2018.case_name, "Dragon v. State")
        self.assertEqual(
            self.docket_d_after_2018.docket_number, "3:15-CV-01455"
        )
        self.assertEqual(len(self.docket_d_after_2018.docket_entries.all()), 0)
        self.assertEqual(self.docket_d_after_2018.source, Docket.HARVARD)

    def test_merge_district_courts_rss_exceptions_after_2018(self):
        """Test merging district RSS exceptions after 2018-4-20

        After 2018-4-20
        District ["miwb", "nceb", "pamd", "cit"]
        Docket doesn't exists
        No docket entries

        Create docket, merge docket entries.
        """
        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court_pamd.pk,
            case_name="Dragon 1 v. State",
            docket_number="3:15-CV-01456",
            pacer_case_id="54312",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2018, month=4, day=21), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(len(self.docket_d_after_2018.docket_entries.all()), 0)
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], self.court_pamd.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)

        docket = Docket.objects.get(pacer_case_id="54312")
        self.assertEqual(docket.case_name, "Dragon 1 v. State")
        self.assertEqual(docket.docket_number, "3:15-CV-01456")

    def test_merging_district_docket_with_entries_before_2018(self):
        """3 Test merge district RSS file before 2018-4-20 into a
        docket with entries.

        Before 2018-4-20
        District
        Docket exists
        Docket entries

        Only merge entry if it doesn't exist, avoid updating metadata.
        """
        d_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Young v. Dragon",
            docket_number="3:17-CV-01473",
            pacer_case_id="9038",
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="2",
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = d_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.de_d_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [d_rss_data_before_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.de_d_before_2018.refresh_from_db()
        self.assertEqual(
            self.de_d_before_2018.docket.case_name, "Young Entry v. Dragon"
        )
        self.assertEqual(
            self.de_d_before_2018.docket.docket_number, "3:87-CV-01400"
        )
        self.assertEqual(
            len(self.de_d_before_2018.docket.docket_entries.all()), 2
        )
        self.assertEqual(
            self.de_d_before_2018.docket.source, Docket.HARVARD_AND_RECAP
        )

    def test_avoid_merging_updating_docket_item_without_docket_entries(
        self,
    ):
        """Test avoid merging or updating the docket when the RSS item doesn't
        contain entries.

        Docket exists
        Docket entries

        Avoid updating metadata.
        """
        d_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Young v. Dragon",
            docket_number="3:17-CV-01473",
            pacer_case_id="9038",
            docket_entries=[],
        )

        build_date = make_aware(
            datetime(year=2017, month=1, day=4), timezone.utc
        )
        self.assertEqual(
            len(self.de_d_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [d_rss_data_before_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)
        self.assertEqual(self.de_d_before_2018.docket.source, Docket.HARVARD)

    def test_add_new_district_rss_before_2018(self):
        """4 Test adds a district RSS file before 2018-4-20, new docket.

        Before: 2018-4-20
        District
        Docket doesn't exist
        No docket entries

        Create docket, merge docket entries.
        """
        d_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Youngs v. Dragon",
            docket_number="3:20-CV-01473",
            pacer_case_id="43562",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_before_2018["docket_entries"][0]["date_filed"]
        dockets = Docket.objects.filter(pacer_case_id="43562")
        self.assertEqual(dockets.count(), 0)
        rds_created, d_created = merge_rss_data(
            [d_rss_data_before_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)
        self.assertEqual(dockets[0].case_name, "Youngs v. Dragon")
        self.assertEqual(dockets[0].docket_number, "3:20-CV-01473")
        self.assertEqual(len(dockets[0].docket_entries.all()), 1)
        self.assertEqual(dockets[0].source, Docket.RECAP)

    def test_avoid_merging_rss_docket_with_entries_district_after_2018(self):
        """5 Test avoid merging district RSS file after 2018-4-20 into a
        docket with entries.

        After 2018-4-20
        District
        Docket exists
        Docket entries

        Don't merge docket entries, avoid updating metadata.
        """
        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Young v. Dragons 2",
            docket_number="3:57-CV-01453",
            pacer_case_id="9038",
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="2",
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.de_d_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)
        self.de_d_before_2018.refresh_from_db()
        self.assertEqual(
            self.de_d_before_2018.docket.case_name, "Young Entry v. Dragon"
        )
        self.assertEqual(
            self.de_d_before_2018.docket.docket_number, "3:87-CV-01400"
        )
        self.assertEqual(
            len(self.de_d_before_2018.docket.docket_entries.all()), 1
        )
        self.assertEqual(self.de_d_before_2018.docket.source, Docket.HARVARD)

    def test_avoid_adding_new_district_rss_after_2018(self):
        """6 Test avoid adding district RSS file after 2018-4-20.

        After 2018-4-20
        District
        Docket doesn't exist
        No docket entries

        Do not create docket, do not merge docket entries.
        """
        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court.pk,
            case_name="Youngs v. Dragon",
            docket_number="3:20-CV-01473",
            pacer_case_id="53432",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], self.court.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)

    # Appellate
    def test_merge_appellate_rss_before_2018(self):
        """7 Test merge an appellate RSS file before 2018-4-20

        Before 2018-4-20
        Appellate
        Docket exists
        No docket entries

        Merge docket entries, avoid updating metadata.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-2532",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.docket_a_before_2018.docket_entries.all()), 0
        )
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.docket_a_before_2018.refresh_from_db()
        self.assertEqual(self.docket_a_before_2018.case_name, "Young v. State")
        self.assertEqual(self.docket_a_before_2018.docket_number, "12-2532")
        self.assertEqual(
            len(self.docket_a_before_2018.docket_entries.all()), 1
        )
        self.assertEqual(
            self.docket_a_before_2018.source, Docket.HARVARD_AND_RECAP
        )

    def test_merging_appellate_rss_after_2018(self):
        """8 Test appellate RSS file after 2018-4-20

        After 2018-4-20
        Appellate
        Docket exists
        No docket entries

        Merge docket entries, avoid updating metadata.
        """
        a_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Dragon 1 v. State",
            docket_number="15-1232",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2018, month=4, day=21), timezone.utc
                    )
                )
            ],
        )

        build_date = a_rss_data_after_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(len(self.docket_a_after_2018.docket_entries.all()), 0)
        rds_created, d_created = merge_rss_data(
            [a_rss_data_after_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.docket_a_after_2018.refresh_from_db()
        self.assertEqual(self.docket_a_after_2018.case_name, "Dragon v. State")
        self.assertEqual(self.docket_a_after_2018.docket_number, "15-1232")
        self.assertEqual(len(self.docket_a_after_2018.docket_entries.all()), 1)
        self.assertEqual(
            self.docket_a_after_2018.source, Docket.HARVARD_AND_RECAP
        )

    def test_avoid_merging_existing_appellate_entry_before_2018(self):
        """9 Test avoid merging appellate RSS file before 2018-4-20, docket
        with entries.

        Before 2018-4-20
        Appellate
        Docket exists
        Docket entries

        Don't merge docket entries, avoid updating metadata.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-3242",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="2",
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.de_a_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.de_a_before_2018.refresh_from_db()
        self.assertEqual(
            self.de_a_before_2018.docket.case_name, "Young Entry v. Dragon"
        )
        self.assertEqual(self.de_a_before_2018.docket.docket_number, "12-3242")
        self.assertEqual(
            len(self.de_a_before_2018.docket.docket_entries.all()), 2
        )
        self.assertEqual(
            self.de_a_before_2018.docket.source, Docket.HARVARD_AND_RECAP
        )

    def test_merge_new_appellate_rss_before_2018(self):
        """10 Merge a new appellate RSS file before 2018-4-20

        Before: 2018-4-20
        Appellate
        Docket doesn't exist
        No docket entries

        Create docket, merge docket entries.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Youngs v. Dragon",
            docket_number="23-4233",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        dockets = Docket.objects.filter(docket_number="23-4233")
        self.assertEqual(dockets.count(), 0)
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)
        self.assertEqual(dockets[0].case_name, "Youngs v. Dragon")
        self.assertEqual(dockets[0].docket_number, "23-4233")
        self.assertEqual(len(dockets[0].docket_entries.all()), 1)
        self.assertEqual(dockets[0].source, Docket.RECAP)

    def test_avoid_merging_existing_appellate_entry_after_2018(self):
        """11 Test avoid merging appellate RSS file after 2018-4-20, docket with
        entries.

        After: 2018-4-20
        Appellate
        Docket exists
        Docket entry exist

        Don't merge the existing entry, avoid updating metadata.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-3242",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="1",
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.de_a_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)

    def test_merging_appellate_docket_with_entries_after_2018(self):
        """Test merge appellate RSS file after 2018-4-20, docket with
        entries.

        After: 2018-4-20
        Appellate
        Docket exists
        Docket entries

        Only merge entry if it doesn't exist, avoid updating metadata.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-3242",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="2",
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.de_a_before_2018.docket.docket_entries.all()), 1
        )
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.de_a_before_2018.refresh_from_db()
        self.assertEqual(
            self.de_a_before_2018.docket.case_name, "Young Entry v. Dragon"
        )
        self.assertEqual(self.de_a_before_2018.docket.docket_number, "12-3242")
        self.assertEqual(
            len(self.de_a_before_2018.docket.docket_entries.all()), 2
        )
        self.assertEqual(
            self.de_a_before_2018.docket.source, Docket.HARVARD_AND_RECAP
        )

    def test_merge_new_appellate_rss_after_2018(self):
        """12 Merge a new appellate RSS file after 2018-4-20

        After: 2018-4-20
        Appellate
        Docket doesn't exist
        No docket entries

        Create docket, merge docket entries, .
        """

        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Youngs v. Dragon",
            docket_number="45-3232",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        dockets = Docket.objects.filter(docket_number="45-3232")
        self.assertEqual(dockets.count(), 0)
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)
        self.assertEqual(dockets.count(), 1)
        self.assertEqual(dockets[0].case_name, "Youngs v. Dragon")
        self.assertEqual(dockets[0].docket_number, "45-3232")
        self.assertEqual(len(dockets[0].docket_entries.all()), 1)
        self.assertEqual(dockets[0].source, Docket.RECAP)

    def test_merging_appellate_docket_with_entries_case_id(self):
        """Test merge an appellate RSS file into a docket with pacer_case_id
        Find docket by docket_number_core, avoid duplicating.
        Merge docket entries, avoid updating metadata.
        """
        a_rss_data_before_2018 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-5674",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number="2",
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    ),
                )
            ],
        )

        build_date = a_rss_data_before_2018["docket_entries"][0]["date_filed"]
        self.assertEqual(
            len(self.docket_a_2018_case_id.docket_entries.all()), 0
        )
        rds_created, d_created = merge_rss_data(
            [a_rss_data_before_2018], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 0)
        self.docket_a_2018_case_id.refresh_from_db()
        self.assertEqual(
            self.docket_a_2018_case_id.case_name, "Young v. State"
        )
        self.assertEqual(self.docket_a_2018_case_id.docket_number, "12-5674")
        self.assertEqual(self.docket_a_2018_case_id.pacer_case_id, "12524")
        self.assertEqual(
            len(self.docket_a_2018_case_id.docket_entries.all()), 1
        )
        self.assertEqual(self.docket_a_2018_case_id.source, Docket.RECAP)

    def test_log_added_items_to_redis(self):
        """Can we log dockets and rds added to redis, adding the previous
        value?
        """
        last_values = log_added_items_to_redis(100, 100, 50)
        self.assertEqual(last_values["total_dockets"], 100)
        self.assertEqual(last_values["total_rds"], 100)
        self.assertEqual(last_values["last_line"], 50)

        last_values = log_added_items_to_redis(50, 80, 100)
        self.assertEqual(last_values["total_dockets"], 150)
        self.assertEqual(last_values["total_rds"], 180)
        self.assertEqual(last_values["last_line"], 100)

        self.r.flushdb()

    def test_merge_mapped_court_rss_before_2018(self):
        """Merge a court mapped RSS file before 2018-4-20

        before: 2018-4-20
        District neb -> nebraskab
        Docket doesn't exist
        No docket entries

        Create docket, merge docket entries, verify is assigned to nebraskab.
        """

        d_rss_data_before_2018 = RssDocketDataFactory(
            court_id="neb",
            case_name="Youngs v. Dragon",
            docket_number="3:20-CV-01473",
            pacer_case_id="43565",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2017, month=1, day=4), timezone.utc
                    )
                )
            ],
        )

        build_date = d_rss_data_before_2018["docket_entries"][0]["date_filed"]
        dockets = Docket.objects.filter(docket_number="3:20-CV-01473")
        self.assertEqual(dockets.count(), 0)
        rds_created, d_created = merge_rss_data(
            [d_rss_data_before_2018], "neb", build_date
        )
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)
        self.assertEqual(dockets.count(), 1)
        self.assertEqual(dockets[0].case_name, "Youngs v. Dragon")
        self.assertEqual(dockets[0].docket_number, "3:20-CV-01473")
        self.assertEqual(len(dockets[0].docket_entries.all()), 1)
        self.assertEqual(dockets[0].source, Docket.RECAP)
        self.assertEqual(dockets[0].court.pk, "nebraskab")

    def test_avoid_merging_district_mapped_court_rss_after_2018(self):
        """Avoid merging a new district RSS file with mapped court
        after 2018-4-20.

        After: 2018-4-20
        District neb -> nebraskab
        Docket doesn't exist
        No docket entries

        Don't merge.
        """

        d_rss_data_after_2018 = RssDocketDataFactory(
            court_id="neb",
            case_name="Youngs v. Dragon",
            docket_number="3:20-CV-01473",
            pacer_case_id="43565",
            docket_entries=[
                RssDocketEntryDataFactory(
                    date_filed=make_aware(
                        datetime(year=2019, month=1, day=4), timezone.utc
                    )
                )
            ],
        )
        build_date = d_rss_data_after_2018["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            [d_rss_data_after_2018], "neb", build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)

    def test_avoid_updating_docket_entry_metadata(self):
        """Test merge appellate RSS file after 2018-4-20, docket with
        entries.

        After: 2018-4-20
        Appellate
        Docket exists
        Docket entries

        Only merge entry if it doesn't exist, avoid updating metadata.
        """

        de_a_unnumbered = DocketEntryWithParentsFactory(
            docket__court=self.court_appellate,
            docket__case_name="Young Entry v. Dragon",
            docket__docket_number="12-3245",
            docket__source=Docket.HARVARD,
            docket__pacer_case_id=None,
            entry_number=None,
            description="Original docket entry description",
            date_filed=make_aware(
                datetime(year=2018, month=1, day=5), timezone.utc
            ),
        )
        RECAPDocumentFactory(
            docket_entry=de_a_unnumbered, description="Opinion Issued"
        )

        a_rss_data_unnumbered = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            case_name="Young v. Dragon",
            docket_number="12-3245",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=None,
                    description="New docket entry description",
                    short_description="Opinion Issued",
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )
        build_date = a_rss_data_unnumbered["docket_entries"][0]["date_filed"]
        self.assertEqual(len(de_a_unnumbered.docket.docket_entries.all()), 1)
        rds_created, d_created = merge_rss_data(
            [a_rss_data_unnumbered], self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 0)
        self.assertEqual(d_created, 0)
        de_a_unnumbered.refresh_from_db()
        self.assertEqual(
            de_a_unnumbered.docket.case_name, "Young Entry v. Dragon"
        )
        self.assertEqual(de_a_unnumbered.docket.docket_number, "12-3245")
        self.assertEqual(
            de_a_unnumbered.description, "Original docket entry description"
        )
        self.assertEqual(len(de_a_unnumbered.docket.docket_entries.all()), 1)
        self.assertEqual(
            de_a_unnumbered.date_filed,
            datetime(year=2018, month=1, day=4).date(),
        )
        self.assertEqual(de_a_unnumbered.docket.source, Docket.HARVARD)

    @patch("cl.corpus_importer.management.commands.troller_bk.logger")
    def test_avoid_cached_items(self, mock_logger):
        """Can we skip a whole file when a cached item is hit?"""

        a_rss_data_0 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="12-3247",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                ),
            ],
        )

        a_rss_data_1 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="12-3245",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )
        a_rss_data_2 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="12-3246",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )

        list_rss_data_1 = [a_rss_data_1, a_rss_data_2]
        list_rss_data_2 = [a_rss_data_0, a_rss_data_1]

        cached_items = RssItemCache.objects.all()
        self.assertEqual(cached_items.count(), 0)
        build_date = a_rss_data_0["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            list_rss_data_1, self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 2)
        self.assertEqual(d_created, 2)
        self.assertEqual(cached_items.count(), 2)

        # Remove recap_sequence_number from the dict to simulate the same item
        del a_rss_data_1["docket_entries"][0]["recap_sequence_number"]
        rds_created, d_created = merge_rss_data(
            list_rss_data_2, self.court_appellate.pk, build_date
        )

        # The file is aborted when a cached item is hit
        self.assertEqual(len(rds_created), 1)
        self.assertEqual(d_created, 1)
        self.assertEqual(cached_items.count(), 3)
        mock_logger.info.assert_called_with(
            f"Finished adding {self.court_appellate.pk} feed. Added {len(rds_created)} RDs."
        )

    @patch(
        "cl.corpus_importer.management.commands.troller_bk.download_file",
        side_effect=mock_download_file,
    )
    def test_download_files_concurrently(self, mock_download):
        """Test the download_files_concurrently method to verify proper
        fetching of the next paths to download from a file. Concurrently
        download these paths and add them to a queue in the original chronological order.
        """
        test_dir = (
            Path(settings.INSTALL_ROOT)
            / "cl"
            / "corpus_importer"
            / "test_assets"
        )
        import_filename = "import.csv"
        import_path = os.path.join(test_dir, import_filename)

        files_queue = Queue()
        threads = []
        files_downloaded_offset = 0

        with open(import_path, "rb") as f:
            files_downloaded_offset = download_files_concurrently(
                files_queue, f.name, files_downloaded_offset, threads
            )
            self.assertEqual(len(threads), 1)
            self.assertEqual(files_downloaded_offset, 3)
            files_downloaded_offset = download_files_concurrently(
                files_queue, f.name, files_downloaded_offset, threads
            )

        for thread in threads:
            thread.join()

        self.assertEqual(len(threads), 2)
        self.assertEqual(files_downloaded_offset, 6)
        self.assertEqual(files_queue.qsize(), 6)

        # Verifies original chronological order.
        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 0)
        self.assertEqual(item_path.split("|")[1], "1575330086")
        files_queue.task_done()

        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 1)
        self.assertEqual(item_path.split("|")[1], "1575333374")
        files_queue.task_done()

        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 2)
        self.assertEqual(item_path.split("|")[1], "1575336978")
        files_queue.task_done()

        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 0)
        self.assertEqual(item_path.split("|")[1], "1575340576")
        files_queue.task_done()

        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 1)
        self.assertEqual(item_path.split("|")[1], "1575344176")
        files_queue.task_done()

        binary, item_path, order = files_queue.get()
        self.assertEqual(order, 2)
        self.assertEqual(item_path.split("|")[1], "1575380176")
        files_queue.task_done()

        self.assertEqual(files_queue.qsize(), 0)

    def test_add_objects_in_bulk(self):
        """Can we properly add related RSS feed objects in bulk?"""

        a_rss_data_0 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="15-3247",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                ),
            ],
        )

        a_rss_data_1 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="15-3245",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )
        a_rss_data_2 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="15-3247",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=2,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )

        a_rss_data_3 = RssDocketDataFactory(
            court_id=self.court_appellate.pk,
            docket_number="12-2532",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=5,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )

        list_rss_data = [
            a_rss_data_0,
            a_rss_data_1,
            a_rss_data_2,
            a_rss_data_3,
        ]
        cached_items = RssItemCache.objects.all()
        self.assertEqual(cached_items.count(), 0)

        build_date = a_rss_data_0["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            list_rss_data, self.court_appellate.pk, build_date
        )

        date_filed, time_filed = localize_date_and_time(
            self.court_appellate.pk, build_date
        )

        # Only two dockets created: 15-3247 and 15-3245, 12-2532 already exists
        self.assertEqual(d_created, 2)
        self.assertEqual(len(rds_created), 4)

        # Compare docket entries and rds created for each docket.
        des_to_compare = [("15-3245", 1), ("15-3247", 2), ("12-2532", 1)]
        for d_number, de_count in des_to_compare:
            docket = Docket.objects.get(docket_number=d_number)
            self.assertEqual(len(docket.docket_entries.all()), de_count)

            # For every docket entry there is one recap document created.
            docket_entries = docket.docket_entries.all()
            for de in docket_entries:
                self.assertEqual(len(de.recap_documents.all()), 1)
                self.assertEqual(de.time_filed, time_filed)
                self.assertEqual(de.date_filed, date_filed)
                self.assertNotEqual(de.recap_sequence_number, "")

            # docket_number_core generated for every docket
            self.assertNotEqual(docket.docket_number_core, "")
            # Slug is generated for every docket
            self.assertNotEqual(docket.slug, "")

            # Verify RECAP source is added to existing and new dockets.
            if d_number == "12-2532":
                self.assertEqual(docket.source, Docket.HARVARD_AND_RECAP)
            else:
                self.assertEqual(docket.source, Docket.RECAP)
                # Confirm date_last_filing is added to each new docket.
                self.assertEqual(docket.date_last_filing, date_filed)

        # BankruptcyInformation is added only on new dockets.
        bankr_objs_created = BankruptcyInformation.objects.all()
        self.assertEqual(len(bankr_objs_created), 3)

        # Compare bankruptcy data is linked correctly to the parent docket.
        bankr_d_1 = BankruptcyInformation.objects.get(
            docket__docket_number=a_rss_data_0["docket_number"]
        )
        self.assertEqual(bankr_d_1.chapter, str(a_rss_data_0["chapter"]))
        self.assertEqual(
            bankr_d_1.trustee_str, str(a_rss_data_0["trustee_str"])
        )

        bankr_d_2 = BankruptcyInformation.objects.get(
            docket__docket_number=a_rss_data_1["docket_number"]
        )
        self.assertEqual(bankr_d_2.chapter, str(a_rss_data_1["chapter"]))
        self.assertEqual(
            bankr_d_2.trustee_str, str(a_rss_data_1["trustee_str"])
        )

        bankr_d_3 = BankruptcyInformation.objects.get(
            docket__docket_number=a_rss_data_3["docket_number"]
        )
        self.assertEqual(bankr_d_3.chapter, str(a_rss_data_3["chapter"]))
        self.assertEqual(
            bankr_d_3.trustee_str, str(a_rss_data_3["trustee_str"])
        )

    def test_avoid_adding_district_dockets_no_pacer_case_id_in_bulk(self):
        """Can we avoid adding district/bankr dockets that don't have a
        pacer_case_id?"""

        a_rss_data_0 = RssDocketDataFactory(
            court_id=self.court_neb.pk,
            docket_number="15-3247",
            pacer_case_id=None,
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                ),
            ],
        )

        a_rss_data_1 = RssDocketDataFactory(
            court_id=self.court_neb.pk,
            docket_number="15-3245",
            pacer_case_id="12345",
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=1,
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                )
            ],
        )

        list_rss_data = [
            a_rss_data_0,
            a_rss_data_1,
        ]

        build_date = a_rss_data_0["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            list_rss_data, self.court_neb.pk, build_date
        )

        # Only one docket created: 15-3245, since 15-3247 don't have pacer_case_id
        self.assertEqual(d_created, 1)
        self.assertEqual(len(rds_created), 1)

        # Compare docket entries and rds created for each docket.
        des_to_compare = [("15-3245", 1)]
        for d_number, de_count in des_to_compare:
            docket = Docket.objects.get(docket_number=d_number)
            self.assertEqual(len(docket.docket_entries.all()), de_count)
            # For every docket entry there is one recap document created.
            docket_entries = docket.docket_entries.all()
            for de in docket_entries:
                self.assertEqual(len(de.recap_documents.all()), 1)
                self.assertNotEqual(de.recap_sequence_number, "")

            # docket_number_core generated for every docket
            self.assertNotEqual(docket.docket_number_core, "")
            # Slug is generated for every docket
            self.assertNotEqual(docket.slug, "")
            self.assertEqual(docket.source, Docket.RECAP)

        # BankruptcyInformation is added only on new dockets.
        bankr_objs_created = BankruptcyInformation.objects.all()
        self.assertEqual(len(bankr_objs_created), 1)

    def test_avoid_adding_existing_entries_by_description(self):
        """Can we avoid adding district/bankr dockets that don't have a
        pacer_case_id?"""

        de = DocketEntryWithParentsFactory(
            docket__court=self.court,
            docket__case_name="Young Entry v. Dragon",
            docket__docket_number="3:87-CV-01409",
            docket__source=Docket.HARVARD,
            docket__pacer_case_id="90385",
            entry_number=None,
            date_filed=make_aware(
                datetime(year=2018, month=1, day=5), timezone.utc
            ),
        )
        RECAPDocumentFactory(docket_entry=de, description="Opinion Issued")
        a_rss_data_0 = RssDocketDataFactory(
            court_id=self.court,
            docket_number="3:87-CV-01409",
            pacer_case_id="90385",
            docket_entries=[
                RssDocketEntryDataFactory(
                    document_number=None,
                    short_description="Opinion Issued",
                    date_filed=make_aware(
                        datetime(year=2018, month=1, day=5), timezone.utc
                    ),
                ),
            ],
        )
        list_rss_data = [
            a_rss_data_0,
        ]
        build_date = a_rss_data_0["docket_entries"][0]["date_filed"]
        rds_created, d_created = merge_rss_data(
            list_rss_data, self.court.pk, build_date
        )

        # No docket entry should be created
        self.assertEqual(d_created, 0)
        self.assertEqual(len(rds_created), 0)


@patch(
    "cl.corpus_importer.management.commands.clean_up_mis_matched_dockets.download_file",
    side_effect=lambda a: {
        "name_abbreviation": "Benedict v. Hankook",
        "name": "Robert BENEDICT, Plaintiff, v. HANKOOK",
        "docket_number": "Civil Action No. 3:17\u2013cv\u2013109",
    },
)
class CleanUpMisMatchedDockets(TestCase):
    """Test find_and_fix_mis_matched_dockets method that finds and fixes mis
    matched opinion dockets added by Harvard importer.
    """

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        # Opinion cluster with mis matched docket.
        cls.cluster = (
            OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(
                    court=cls.court,
                    source=Docket.HARVARD,
                    case_name="Glover vs Pridemore",
                    case_name_full="Glover vs Pridemore",
                    docket_number="2:17-cv-00109",
                    pacer_case_id="12345",
                ),
                case_name="Foo v. Bar",
                date_filed=date.today(),
            ),
        )
        cf = ContentFile(b"Hello World att 1")
        cls.cluster[0].filepath_json_harvard.save("file.json", cf)

        # Opinion cluster with correct docket
        cluster_2 = (
            OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(
                    court=cls.court,
                    source=Docket.HARVARD,
                    case_name="Foo v. Bar",
                    case_name_full="Foo v. Bar",
                    docket_number="2:17-cv-00109",
                    pacer_case_id=None,
                ),
                case_name="Foo v. Bar",
                date_filed=date.today(),
            ),
        )
        cf = ContentFile(b"Hello World att 1")
        cluster_2[0].filepath_json_harvard.save("file.json", cf)

    def test_find_mis_matched_docket(self, mock_download_ia):
        """Test only find and report mis matched dockets."""

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 2)
        mis_matched_dockets = find_and_fix_mis_matched_dockets(fix=False)
        self.assertEqual(len(mis_matched_dockets), 1)
        self.assertEqual(dockets.count(), 2)

    def test_find_and_fix_mis_matched_dockets(self, mock_download_ia):
        """Test find and fix mis matched dockets"""

        cluster = self.cluster[0]
        mis_matched_docket = cluster.docket
        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 2)
        mis_matched_dockets = find_and_fix_mis_matched_dockets(fix=True)
        self.assertEqual(len(mis_matched_dockets), 1)
        self.assertEqual(dockets.count(), 3)

        cluster.refresh_from_db()
        self.assertEqual(
            cluster.docket.docket_number, "Civil Action No. 3:17–cv–109"
        )
        self.assertEqual(cluster.docket.case_name, "Benedict v. Hankook")
        self.assertEqual(cluster.docket.source, Docket.HARVARD)

        # The mis matched docket is preserved, fix its source to RECAP.
        mis_matched_docket.refresh_from_db()
        self.assertEqual(mis_matched_docket.source, Docket.RECAP)
