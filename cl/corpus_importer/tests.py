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
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db.models.signals import post_save
from django.utils.timezone import make_aware, now
from eyecite.tokenizers import HyperscanTokenizer
from factory import RelatedFactory
from juriscraper.lib.string_utils import harmonize, titlecase

from cl.corpus_importer.court_regexes import match_court_string
from cl.corpus_importer.factories import (
    CaseBodyFactory,
    CaseLawCourtFactory,
    CaseLawFactory,
    CitationFactory,
    RssDocketDataFactory,
    RssDocketEntryDataFactory,
)
from cl.corpus_importer.import_columbia.columbia_utils import fix_xml_tags
from cl.corpus_importer.import_columbia.parse_opinions import (
    get_state_court_object,
)
from cl.corpus_importer.management.commands.clean_up_mis_matched_dockets import (
    find_and_fix_mis_matched_dockets,
)
from cl.corpus_importer.management.commands.columbia_merge import (
    process_cluster,
)
from cl.corpus_importer.management.commands.harvard_merge import (
    combine_non_overlapping_data,
    fetch_non_harvard_data,
    merge_cluster_dates,
    merge_opinion_clusters,
    update_cluster_source,
    update_docket_source,
)
from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_body_content,
    parse_harvard_opinions,
    validate_dt,
)
from cl.corpus_importer.management.commands.normalize_judges_opinions import (
    normalize_authors_in_opinions,
    normalize_panel_in_opinioncluster,
)
from cl.corpus_importer.management.commands.troller_bk import (
    download_files_concurrently,
    log_added_items_to_redis,
    merge_rss_data,
)
from cl.corpus_importer.signals import (
    handle_update_latest_case_id_and_schedule_iquery_sweep,
    update_latest_case_id_and_schedule_iquery_sweep,
)
from cl.corpus_importer.tasks import (
    compute_next_binary_probe,
    generate_ia_json,
    get_and_save_free_document_report,
    iquery_pages_probing,
)
from cl.corpus_importer.utils import (
    ClusterSourceException,
    DocketSourceException,
    compare_documents,
    get_start_of_quarter,
    merge_case_names,
    merge_docket_numbers,
    merge_judges,
    merge_strings,
    winnow_case_name,
)
from cl.lib.pacer import process_docket_data
from cl.lib.redis_utils import get_redis_interface
from cl.lib.timezone_helpers import localize_date_and_time
from cl.people_db.factories import PersonWithChildrenFactory, PositionFactory
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
    find_all_judges,
    find_just_name,
)
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.models import UPLOAD_TYPE
from cl.recap_rss.models import RssItemCache
from cl.scrapers.models import PACERFreeDocumentRow
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterFactoryMultipleOpinions,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionClusterWithParentsFactory,
    OpinionWithChildrenFactory,
    RECAPDocumentFactory,
)
from cl.search.models import (
    SOURCES,
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
from cl.tests.fakes import FakeCaseQueryReport, FakeFreeOpinionReport

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


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

    @patch(
        "cl.corpus_importer.tasks.get_or_cache_pacer_cookies",
        return_value=None,
    )
    def test_get_and_save_free_document_report(self, mock_cookies) -> None:
        """Test the retrieval and storage of free document report data."""

        with patch(
            "cl.corpus_importer.tasks.FreeOpinionReport",
            new=FakeFreeOpinionReport,
        ):
            get_and_save_free_document_report(
                "cand", now().date(), now().date()
            )

        row = PACERFreeDocumentRow.objects.all()
        self.assertEqual(row.count(), 1)
        self.assertEqual(row[0].court_id, "cand")
        self.assertEqual(row[0].docket_number, "5:18-ap-07075")
        self.assertTrue(row[0].description)
        self.assertTrue(row[0].date_filed)
        self.assertTrue(row[0].document_number)
        self.assertTrue(row[0].nature_of_suit)
        self.assertTrue(row[0].pacer_case_id)
        self.assertTrue(row[0].pacer_doc_id)
        self.assertTrue(row[0].pacer_seq_no)


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
        self.get_fix_list_patch = patch(
            "cl.corpus_importer.management.commands.harvard_opinions.get_fix_list"
        )
        self.get_fix_list = self.get_fix_list_patch.start()

        # Default values for Harvard Tests
        self.filepath_list_func.return_value = ["/one/fake/filepath.json"]
        self.find_court_func.return_value = ["harvard"]
        self.get_fix_list.return_value = []

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
        cites = eyecite.get_citations(
            case_law["citations"][0]["cite"], tokenizer=HYPERSCAN_TOKENIZER
        )
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

    @classmethod
    def restart_troller_log(cls):
        r = get_redis_interface("STATS")
        key = r.keys("troller_bk:log")
        if key:
            r.delete(*key)

    def setUp(self) -> None:
        self.restart_troller_log()

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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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

        self.restart_troller_log()

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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
            list_rss_data_1, self.court_appellate.pk, build_date
        )
        self.assertEqual(len(rds_created), 2)
        self.assertEqual(d_created, 2)
        self.assertEqual(cached_items.count(), 2)

        # Remove recap_sequence_number from the dict to simulate the same item
        del a_rss_data_1["docket_entries"][0]["recap_sequence_number"]
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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
        rds_created, d_created = async_to_sync(merge_rss_data)(
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


class HarvardMergerTests(TestCase):
    def setUp(self):
        """Setup harvard merger tests"""
        self.read_json_patch = patch(
            "cl.corpus_importer.management.commands.harvard_merge.read_json"
        )
        self.read_json_func = self.read_json_patch.start()

    def tearDown(self) -> None:
        """Tear down patches and remove added objects"""
        Docket.objects.all().delete()
        self.read_json_patch.stop()

    def test_merger(self):
        """Can we identify opinions correctly even when they are slightly
        different"""

        case_data = {
            "name": "CANNON v. THE STATE",
            "name_abbreviation": "Cannon v. State",
            "decision_date": "1944-11-18",
            "docket_number": "30614",
            "casebody": {
                "status": "ok",
                "data": '<casebody firstpage="757" lastpage="758" xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1">\n  <docketnumber id="b795-7">30614.</docketnumber>\n  <parties id="AAY">CANNON <em>v. </em>THE STATE.</parties>\n  <decisiondate id="b795-9">Decided November 18, 1944.</decisiondate>\n  <attorneys id="b796-4"><page-number citation-index="1" label="758">*758</page-number><em>B. B. Giles, </em>for plaintiff in error.</attorneys>\n  <attorneys id="b796-5"><em>Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, </em>contra.</attorneys>\n  <opinion type="majority">\n    <author id="b796-6">Broyles, C. J.</author>\n    <p id="Auq">(After stating the foregoing facts.) After the-disposal of counts 2 and 3, the only charge before the court and jury was that the defendant had sold distilled spirits and alcohol as a retail dealer, without first obtaining a license from the State Revenue Commissioner. The evidence adduced to show the guilt, of the accused on count 1 was wholly circumstantial, and was insufficient to exclude every reasonable hypothesis except that of his-guilt, and it failed to show beyond a reasonable doubt that he had sold distilled spirits or alcohol. The cases of <em>Thomas </em>v. <em>State, </em>65 <em>Ga. App. </em>749 (16 S. E. 2d, 447), and <em>Martin </em>v. <em>State, </em>68 <em>Ga. App. </em>169 (22 S. E. 2d, 193), cited in behalf of the defendant in error, are distinguished by their facts from this case. The verdict was-contrary to law and the evidence; and the overruling of the certiorari was error. <em>Judgment reversed.</em></p>\n    <judges id="Ae85">\n      <em>MacIntyre, J., concurs.</em>\n    </judges>\n  </opinion>\n  <opinion type="concurrence">\n    <author id="b796-7">Gardner, J.,</author>\n    <p id="AK2">concurring specially: Under the record the judgment should be reversed for another reason. Since the jury, based on the same evidence, found the defendant not guilty on count 2 for possessing liquors, and a verdict finding him guilty on count 1 for selling intoxicating liquors, the verdicts are repugnant and void as being inconsistent verdicts by the same jury based on the same \'evidence. <em>Britt </em>v. <em>State, </em>36 <em>Ga. App. </em>668 (137 S. E. 791), and cit.; <em>Kuck </em>v. <em>State, </em>149 <em>Ga. </em>191 (99 S. E. 622). I concur in the reversal for this additional reason.</p>\n  </opinion>\n</casebody>\n',
            },
        }
        self.read_json_func.return_value = case_data

        lead = """<p>The overruling of the certiorari was error.</p>
            <p><center>                       DECIDED NOVEMBER 18, 1944.</center>
            John Cannon was tried in the criminal court of Fulton County on an accusation containing three counts. Count I charged that in said county on July 24, 1943, he "did engage in and sell, as a retail dealer, distilled spirits and alcohol, without first obtaining a license from the State Revenue Commissioner of the State of Georgia." Count 2 charged that on July 24, 1943, he possessed forty-eight half pints and three pints of whisky in Fulton County, and had not been licensed by the State Revenue Commissioner to sell whisky as a retail or wholesale dealer. Count 3 charged that on September 24, 1943, in said county, he sold malt beverages as a retail dealer, without first securing a license from the State Revenue Commissioner. On the trial, after the close of the State's evidence, counsel for the accused made a motion that count 2 be stricken, and that a verdict for the defendant be directed on counts 1 and 3. The court sustained the motion as to counts 2 and 3, but overruled it as to count 1. The jury returned a verdict of guilty on count 1, and of not guilty on counts 2 and 3. Subsequently the defendant's certiorari was overruled by a judge of the superior court and that judgment is assigned as error. <span class="star-pagination">*Page 758</span>
            After the disposal of counts 2 and 3, the only charge before the court and jury was that the defendant had sold distilled spirits and alcohol as a retail dealer, without first obtaining a license from the State Revenue Commissioner. The evidence adduced to show the guilt of the accused on count 1 was wholly circumstantial, and was insufficient to exclude every reasonable hypothesis except that of his guilt, and it failed to show beyond a reasonable doubt that he had sold distilled spirits or alcohol. The cases of <em>Thomas</em> v. <em>State,</em> <cross_reference><span class="citation no-link">65 Ga. App. 749</span></cross_reference> (<cross_reference><span class="citation" data-id="3407553"><a href="/opinion/3412403/thomas-v-state/">16 S.E.2d 447</a></span></cross_reference>), and <em>Martin</em> v. <em>State,</em> <cross_reference><span class="citation no-link">68 Ga. App. 169</span></cross_reference> (<cross_reference><span class="citation" data-id="3405716"><a href="/opinion/3410794/martin-v-state/">22 S.E.2d 193</a></span></cross_reference>), cited in behalf of the defendant in error, are distinguished by their facts from this case. The verdict was contrary to law and the evidence; and the overruling of the certiorari was error.</p>
            <p><em>Judgment reversed. MacIntyre, J., concurs.</em></p>"""
        concurrence = """<p>Under the record the judgment should be reversed for another reason. Since the jury, based on the same evidence, found the defendant not guilty on count 2 for possessing liquors, and a verdict finding him guilty on count 1 for selling intoxicating liquors, the verdicts are repugnant and void as being inconsistent verdicts by the same jury based on the same evidence. <em>Britt</em> v. <em>State,</em> <cross_reference><span class="citation no-link">36 Ga. App. 668</span></cross_reference>
            (<cross_reference><span class="citation no-link">137 S.E. 791</span></cross_reference>), and cit.; <em>Kuck</em> v. <em>State,</em> <cross_reference><span class="citation" data-id="5582722"><a href="/opinion/5732248/kuck-v-state/">149 Ga. 191</a></span></cross_reference>
            (<cross_reference><span class="citation no-link">99 S.E. 622</span></cross_reference>). I concur in the reversal for this additional reason.</p>"""

        cluster = OpinionClusterFactoryMultipleOpinions(
            source=SOURCES.COLUMBIA_ARCHIVE,
            docket=DocketFactory(source=Docket.COLUMBIA),
            sub_opinions__data=[
                {
                    "type": "020lead",
                    "html_with_citations": lead,
                    "author_str": "Broyles",
                },
                {
                    "type": "030concurrence",
                    "html_with_citations": concurrence,
                    "author_str": "Gardner",
                },
            ],
        )

        self.assertEqual(
            cluster.attorneys,
            "",
            msg="This value should be empty unless you have specified it in "
            "the factory.",
        )

        self.assertEqual(
            cluster.judges,
            "",
            msg="This value should be empty unless you have specified it in "
            "the factory.",
        )

        self.assertEqual(cluster.sub_opinions.all().count(), 2)

        merge_opinion_clusters(cluster_id=cluster.id)

        cluster.refresh_from_db()

        self.assertEqual(cluster.sub_opinions.all().count(), 2)

        self.assertEqual(
            cluster.attorneys,
            "B. B. Giles, for plaintiff in error., Lindley W. Gamp, "
            "solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, "
            "contra.",
        )

        self.assertEqual(
            cluster.judges,
            "Broyles, Gardner, MacIntyre",
        )

    def test_non_overlapping(self):
        """Can we find fields that need merging"""

        case_data = {
            "casebody": {
                "data": '<casebody> <attorneys><page-number citation-index="1" label="758">*758</page-number><em>B. B. Giles, </em>for plaintiff in error.</attorneys>\n  <attorneys id="b796-5"><em>Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, </em>contra.</attorneys>\n  <opinion type="majority"> a simple opinion</opinion>\n</casebody>\n',
            },
        }
        self.read_json_func.return_value = case_data

        cluster = OpinionClusterFactoryMultipleOpinions(
            docket=DocketFactory(),
            attorneys="B. B. Giles, Lindley W. Gamp, and John A. Boyhin",
        )
        clean_dictionary = combine_non_overlapping_data(cluster, case_data)
        self.assertEqual(
            clean_dictionary,
            {
                "attorneys": (
                    "B. B. Giles, for plaintiff in error., Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, contra.",
                    "B. B. Giles, Lindley W. Gamp, and John A. Boyhin",
                )
            },
            msg="Should find differences to merge",
        )

        # Test that we can ignore matching fields
        cluster = OpinionClusterFactoryMultipleOpinions(
            docket=DocketFactory(),
            attorneys="B. B. Giles, for plaintiff in error., Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, contra.",
        )
        clean_dictionary = combine_non_overlapping_data(cluster, case_data)
        self.assertEqual(clean_dictionary, {}, msg="Attorneys are the same")

    def test_docket_number_merger(self):
        """Can we choose the correct docket number"""
        docket = DocketFactory(docket_number="17-3000")
        cluster = OpinionClusterWithParentsFactory(id=4, docket=docket)
        updated_docket_number = merge_docket_numbers(
            cluster, "Master Docket No. 17-3000L"
        )
        docket.docket_number = updated_docket_number
        docket.save()
        docket.refresh_from_db()
        self.assertEqual(docket.docket_number, "Master Docket 17-3000L")

    def test_sources_query(self):
        """Test query for Non Harvard Sources"""

        OpinionClusterFactory(
            source=SOURCES.COLUMBIA_ARCHIVE,
            docket=DocketFactory(source=Docket.COLUMBIA),
            id=1,
            filepath_json_harvard="/the/file/path.json",
        )
        OpinionClusterFactory(
            source=SOURCES.HARVARD_CASELAW,
            docket=DocketFactory(source=Docket.HARVARD),
            id=2,
            filepath_json_harvard="/a/file/path.json",
        )
        OpinionClusterFactory(
            source=SOURCES.COLUMBIA_ARCHIVE_M_HARVARD,
            docket=DocketFactory(source=Docket.HARVARD_AND_COLUMBIA),
            id=3,
            filepath_json_harvard="/some/file/path.json",
        )
        OpinionClusterFactory(
            source=SOURCES.COURT_WEBSITE,
            docket=DocketFactory(source=Docket.SCRAPER),
            id=4,
            filepath_json_harvard="/my/file/path.json",
        )
        OpinionClusterFactory(
            source=SOURCES.COURT_WEBSITE,
            docket=DocketFactory(source=Docket.SCRAPER),
            id=5,
            filepath_json_harvard=None,
        )
        OpinionClusterFactory(
            docket=DocketFactory(source=Docket.HARVARD),
            id=6,
            filepath_json_harvard="",
        )

        cluster_ids = (
            OpinionCluster.objects.filter(
                docket__source__in=[
                    s[0]
                    for s in Docket.SOURCE_CHOICES
                    if "Harvard" not in s[1]
                ],
                filepath_json_harvard__isnull=False,
            )
            .exclude(filepath_json_harvard__exact="")
            .values_list("id", flat=True)
        )

        self.assertEqual([1, 4], list(sorted(cluster_ids)))

        case_data = {
            "docket_number": "345",
            "name_abbreviation": "A v. B",
            "name": "A v. B",
            "casebody": {
                "data": '<casebody><opinion type="majority">An opinion</opinion></casebody>'
            },
        }

        self.read_json_func.return_value = case_data

        cluster_ids = OpinionCluster.objects.filter(
            docket__source__in=[
                s[0] for s in Docket.SOURCE_CHOICES if "Harvard" not in s[1]
            ],
            filepath_json_harvard__isnull=False,
        ).values_list("id", flat=True)

        for id in cluster_ids:
            merge_opinion_clusters(cluster_id=id)

        self.assertEqual([1, 4, 5], list(sorted(cluster_ids)))

    def test_add_opinions_without_authors_in_cl(self):
        """Can we add opinion and update authors"""

        cluster = OpinionClusterFactoryMultipleOpinions(
            source=SOURCES.COLUMBIA_ARCHIVE,
            docket=DocketFactory(source=Docket.COLUMBIA),
            sub_opinions__data=[
                {"author_str": "", "plain_text": "My opinion"},
                {"author_str": "", "plain_text": "I disagree"},
            ],
        )
        case_data = {
            "docket_number": "345",
            "name_abbreviation": "A v. B",
            "name": "A v. B",
            "casebody": {
                "data": '<casebody> <opinion type="majority"> '
                "<author>Broyles, C. J.</author>My opinion</opinion>"
                ' <opinion type="dissent"><author>Gardner, J.,</author>'
                "I disagree </opinion>"
                "</casebody>",
            },
        }
        self.read_json_func.return_value = case_data

        author_query = Opinion.objects.filter(
            cluster_id=cluster.id
        ).values_list("author_str", flat=True)

        authors = list(author_query)

        self.assertEqual(authors, ["", ""])

        cluster_ids = OpinionCluster.objects.filter(
            docket__source__in=[
                s[0] for s in Docket.SOURCE_CHOICES if "Harvard" not in s[1]
            ],
            filepath_json_harvard__isnull=False,
        ).values_list("id", flat=True)

        for id in cluster_ids:
            merge_opinion_clusters(cluster_id=id)

        cluster.refresh_from_db()

        author_query = Opinion.objects.filter(
            cluster_id=cluster.id
        ).values_list("author_str", flat=True)

        authors = list(author_query)

        self.assertEqual(
            Opinion.objects.filter(cluster_id=cluster.id).count(),
            2,
            msg="Oops",
        )

        self.assertNotEqual(
            Opinion.objects.filter(cluster_id=cluster.id)[0].xml_harvard, ""
        )

        self.assertEqual(cluster.docket.source, Docket.HARVARD_AND_COLUMBIA)

        self.assertEqual(authors, ["Broyles", "Gardner"])

    def test_add_opinions_with_authors_in_cl(self):
        """Can we update an opinion and leave author_str alone if already
        assigned"""

        cluster = OpinionClusterFactoryMultipleOpinions(
            source=SOURCES.COLUMBIA_ARCHIVE,
            docket=DocketFactory(source=Docket.COLUMBIA),
            sub_opinions__data=[
                {"author_str": "Broyles", "plain_text": "My opinion"},
                {"author_str": "Gardner", "plain_text": "I disagree"},
            ],
        )
        case_data = {
            "docket_number": "345",
            "name_abbreviation": "A v. B",
            "name": "A v. B",
            "casebody": {
                "data": '<casebody> <opinion type="majority"> '
                "<author>Broyles, C. J.</author>My opinion</opinion>"
                ' <opinion type="dissent"><author>Gardner, J.,</author>'
                "I disagree </opinion>"
                "</casebody>",
            },
        }

        self.read_json_func.return_value = case_data

        author_query = Opinion.objects.filter(
            cluster_id=cluster.id
        ).values_list("author_str", flat=True)

        self.assertEqual(sorted(list(author_query)), ["Broyles", "Gardner"])

        merge_opinion_clusters(cluster_id=cluster.id)

        cluster.refresh_from_db()
        author_query = Opinion.objects.filter(
            cluster_id=cluster.id
        ).values_list("author_str", flat=True)

        self.assertEqual(
            Opinion.objects.filter(cluster_id=cluster.id).count(),
            2,
            msg="Oops",
        )

        self.assertNotEqual(
            Opinion.objects.filter(cluster_id=cluster.id)[0].xml_harvard, ""
        )

        self.assertEqual(cluster.docket.source, Docket.HARVARD_AND_COLUMBIA)

        self.assertEqual(sorted(list(author_query)), ["Broyles", "Gardner"])

    def test_merge_overlap_judges(self):
        """Can we merge overlap judge names?"""

        for item in [
            # Format: (cl judge, harvard prepared data, expected output)
            # CL item #4575556
            (
                "Barbera",
                "Barbera",
                "",  # No need to update value, expected output is empty
            ),
            # CL item #4573873
            (
                "Simpson, J. ~ Concurring Opinion by Pellegrini, Senior Judge",
                "Simpson",
                "",  # No need to update, cl data is better than harvard data
            ),
            (
                "January 1st 2020",  # CL  #bad data example
                "Simpson, J. ~ Concurring Opinion by Pellegrini, Senior Judge",
                # Harvard
                "Pellegrini, Simpson",  # harvard data is good, save it
            ),
            # CL item #4576003
            (
                "French, J.",
                "Fischer, French, Kennedy",
                "Fischer, French, Kennedy",
            ),
            # CL item #4576003
            (
                "Leavitt, President Judge",
                "Leavitt",
                "",  # extracted data is the same, no need to update
            ),
            # CL item #1301211
            (
                "Mikell",
                "MlKELL",  # there is a typo in the name, but it is very similar, we shouldn't be throwing an exception
                "Mikell",
            ),
        ]:
            # Pass a fake cluster id, it is only necessary to log a message when
            # skip_judge_merger option is set
            data_to_update = merge_judges((item[1], item[0]), cluster_id=12345)
            self.assertEqual(data_to_update.get("judges", ""), item[2])

    def test_merge_overlap_casenames(self):
        """Can we merge overlap case names?"""

        for item in [
            # CL item #4571581
            (
                {
                    "name": "Vivian PEREZ, Administratrix (Estate of Andres "
                    "Burgos) v. METROPOLITAN DISTRICT COMMISSION",
                    "name_abbreviation": "Perez v. Metro. Dist. Comm'n",
                },
                {
                    "cl_case_name": "Perez v. Metropolitan District Commisssion",
                    "cl_case_name_full": "",
                },
                {
                    "expected_case_name": "",
                    "expected_case_name_full": "Vivian PEREZ, Administratrix "
                    "(Estate of Andres Burgos) v. "
                    "METROPOLITAN DISTRICT "
                    "COMMISSION",
                },
            ),
            # CL item #4574207
            (
                {
                    "name": "Randy WEYERMAN v. FREEMAN EXPOSITIONS, INC., "
                    "Employer, and Old Republic Insurance Company, "
                    "Insurance Carrier",
                    "name_abbreviation": "Weyerman v. Freeman Expositions, "
                    "Inc.",
                },
                {
                    "cl_case_name": "Weyerman v. Freeman Expositions",
                    "cl_case_name_full": "",
                },
                {
                    "expected_case_name": "Weyerman v. Freeman Expositions, "
                    "Inc.",
                    "expected_case_name_full": "Randy WEYERMAN v. FREEMAN "
                    "EXPOSITIONS, INC., Employer, "
                    "and Old Republic Insurance "
                    "Company, Insurance Carrier",
                },
            ),
            # CL item #4576005
            (
                {
                    "name": "The STATE EX REL. MURRAY v. STATE EMPLOYMENT "
                    "RELATIONS BOARD",
                    "name_abbreviation": "State ex rel. Murray v. State "
                    "Emp't Relations Bd",
                },
                {
                    "cl_case_name": "State ex rel. Murray v. State Emp. "
                    "Relations Bd. (Slip Opinion)",
                    "cl_case_name_full": "",
                },
                {
                    "expected_case_name": "The State Ex Rel. Murray v. State "
                    "Employment Relations Board",
                    "expected_case_name_full": "State Ex Rel. Murray v. "
                    "State Emp. Relations Bd. ("
                    "Slip Opinion)",
                },
            ),
        ]:
            cluster = OpinionClusterWithParentsFactory(
                case_name=item[1].get("cl_case_name"),
                case_name_full=item[1].get("cl_case_name_full"),
            )

            data_to_update = merge_case_names(
                cluster,
                item[0],
                case_name_key="name_abbreviation",
                case_name_full_key="name",
            )

            self.assertEqual(
                data_to_update.get("case_name", ""),
                item[2].get("expected_case_name"),
            )

            self.assertEqual(
                data_to_update.get("case_name_full", ""),
                item[2].get("expected_case_name_full"),
            )

    def test_merge_date_filed(self):
        """Can we merge date filed?"""

        # Item format: (harvard_decision_date, cl date_filed, expected output)
        for item in [
            # CL item #4549197
            ("2018-10-23", date(2018, 11, 1), date(2018, 10, 23)),
            # CL item #4549214
            ("2018-10-19", date(2018, 11, 1), date(2018, 10, 19)),
            # CL item #4548724
            ("2018-10-30", date(2018, 11, 6), date(2018, 10, 30)),
        ]:
            cluster = OpinionClusterWithParentsFactory(
                date_filed=item[1],
                docket=DocketFactory(source=Docket.SCRAPER),
            )

            data_to_update = merge_cluster_dates(
                cluster, "date_filed", (item[0], item[1])
            )
            cluster.refresh_from_db()

            self.assertEqual(data_to_update.get("date_filed"), item[2])

    def test_update_docket_source(self):
        """Can we update docket source?"""

        docket_1 = DocketFactory(source=Docket.RECAP)
        cluster_1 = OpinionClusterWithParentsFactory(docket=docket_1)
        update_docket_source(cluster_1)
        docket_1.refresh_from_db()
        self.assertEqual(docket_1.source, Docket.HARVARD_AND_RECAP)

        with self.assertRaises(DocketSourceException):
            # Raise DocketSourceException if the initial source already contains
            # Harvard.
            docket_2 = DocketFactory(
                source=Docket.RECAP_AND_SCRAPER_AND_HARVARD
            )
            cluster_2 = OpinionClusterWithParentsFactory(docket=docket_2)
            update_docket_source(cluster_2)
            docket_2.refresh_from_db()

    def test_update_cluster_source(self):
        """Can we update cluster source?"""

        cluster_1 = OpinionClusterWithParentsFactory(
            source=SOURCES.COURT_WEBSITE
        )
        update_cluster_source(cluster_1)
        cluster_1.refresh_from_db()
        self.assertEqual(cluster_1.source, SOURCES.COURT_M_HARVARD)

        with self.assertRaises(ClusterSourceException):
            cluster_2 = OpinionClusterWithParentsFactory(
                source=SOURCES.INTERNET_ARCHIVE
            )
            update_cluster_source(cluster_2)
            cluster_2.refresh_from_db()

    def test_merge_strings(self):
        """Can we choose the best string to fill the field?"""
        cluster = OpinionClusterWithParentsFactory(
            attorneys="A. G. Allen and O. N. Gibson, for appellants."
        )

        changed_values_dictionary = {
            "attorneys": (
                "A. G. Allen and O. N. Gibson, for appellants., H. G. Brome "
                "and C. H. Harkins, for respondents.",
                "A. G. Allen and O. N. Gibson, for appellants.",
            )
        }

        data_to_update = merge_strings(
            "attorneys", changed_values_dictionary.get("attorneys")
        )

        cluster.refresh_from_db()

        self.assertEqual(
            data_to_update.get("attorneys"),
            "A. G. Allen and O. N. Gibson, for appellants., H. G. Brome and "
            "C. H. Harkins, for respondents.",
        )

    def test_judge_name_extraction(self):
        """Can we extract out judges properly"""

        test_pairs = [
            (
                # Test if we are tripped up by multiple judge names in tag
                "ARNOLD, Circuit Judge, with whom BRIGHT, Senior Circuit Judge, and McMILLIAN and MAGILL, Circuit Judges, join,:",
                "Arnold",
            ),
            (
                # Test if we have issues with accents
                "POCHÉ, Acting P. J.",
                "Poche",
            ),
            (
                # Test Scottish name and different pattern
                "CHIEF JUSTICE McGRATH",
                "McGRATH",
            ),
            (
                # Test a common word issue, with Common Style
                "PAGE, J.",
                "Page",
            ),
            (
                # Test if CAPITALIZED words in long string causes issue
                "J. Michael Seabright, Chief United States District Judge         I.           INTRODUCTION",
                "Seabright",
            ),
            (
                # Test Surnames with numerals
                "WILLIAM H. PAULEY III, United States District Judge:",
                "Pauley III",
            ),
            (
                # Test apostrophes
                "Joseph E. O\u2019Neill, Presiding Judge.",
                "O'Neill",
            ),
            (
                # Test Hyphenated names
                "BAMATTRE-MANOUKIAN, Acting P. J.\u2014 2",
                "Bamattre-Manoukian",
            ),
            (
                # Test common who word name
                "De Vane, District Judge",
                "De Vane",
            ),
            (
                # Test another common two word name, titled
                "Van Goth, District Judge",
                "Van Goth",
            ),
            (
                # Test common two word, capitalized
                "VAN GOGH, District Judge",
                "Van Gogh",
            ),
            (
                # Test Simple name
                "Judge Smith",
                "Smith",
            ),
            (
                # Test honorific
                "Hon. Gonzalo P. Curiel, United States District Judge",
                "Curiel",
            ),
            (
                # Test abbreviated middle name
                "Terrence L. O'Brien, Circuit Judge",
                "O'Brien",
            ),
        ]
        for pair in test_pairs:
            author_str = titlecase(find_just_name(pair[0]))
            self.assertEqual(pair[1], author_str, msg=f"Failed: {pair[1]}")

    def test_panel_extraction(self):
        """Can we extract out judges properly"""

        test_pairs = [
            (
                # Test if we are tripped up by multiple judge names in tag
                "ARNOLD, Circuit Judge, with whom BRIGHT, Senior Circuit Judge, and McMILLIAN and MAGILL, Circuit Judges, join,:",
                ["ARNOLD", "BRIGHT", "MAGILL", "McMILLIAN"],
            ),
            (
                # Normal and
                "Judge MARQUEZ and Judge VOGT concur",
                ["MARQUEZ", "VOGT"],
            ),
            (
                # Test Suffixes
                "Judge MARQUEZ IV and Judge VOGT concur",
                ["MARQUEZ IV", "VOGT"],
            ),
            (
                "DENNIS joined by GRAVES, Circuit JUDGE",
                ["DENNIS", "GRAVES"],
            ),
            (
                "DENNIS joined by GRAVES, Circuit JUDGE",
                ["DENNIS", "GRAVES"],
            ),
            (
                "Present: Qua, C.J., Lummus, Dolan, Spalding, & Williams, JJ.",
                ["Dolan", "Lummus", "Qua", "Spalding", "Williams"],
            ),
            (
                "Argued before VAN BRUNT, P. J., and BARRETT, RUMSEY, PATTERSON, and O’BRIEN, JJ.",
                ["BARRETT", "O'BRIEN", "PATTERSON", "RUMSEY", "VAN BRUNT"],
            ),
        ]
        for pair in test_pairs:
            judge_list = find_all_judges(pair[0])
            self.assertEqual(pair[1], judge_list, msg=f"Failed: {pair[1]}")

    def test_process_harvard_data(self):
        """Can we correctly parse the data from json harvard?"""

        case_data = {
            "name": "CANNON v. THE STATE",
            "name_abbreviation": "Cannon v. State",
            "decision_date": "1944-11-18",
            "docket_number": "30614",
            "casebody": {
                "status": "ok",
                "data": '<casebody firstpage="757" lastpage="758" '
                'xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr'
                ".US_Case_Law"
                '.Schema.Case_Body:v1">\n  <docketnumber '
                'id="b795-7">30614.</docketnumber>\n  <parties '
                'id="AAY">CANNON <em>v. </em>THE STATE.</parties>\n  '
                '<decisiondate id="b795-9">Decided November 18, '
                '1944.</decisiondate>\n  <attorneys id="b796-4"><page-number '
                'citation-index="1" label="758">*758</page-number><em>B. B. '
                "Giles, </em>for plaintiff in error.</attorneys>\n  "
                '<attorneys id="b796-5"><em>Lindley W. Gamp, solicitor, '
                "John A. Boyhin, solicitor-general,. Durwood T. Bye, "
                '</em>contra.</attorneys>\n  <syllabus id="b283-9"> This is '
                "a syllabus example.</syllabus><opinion "
                'type="majority">\n'
                '<author id="b796-6">Broyles, C. J.</author>\n  <p>Sample '
                'text</p>   <judges id="Ae85">\n      <em>MacIntyre, J., '
                "concurs.</em>\n    </judges>\n  </opinion>\n  <opinion "
                'type="concurrence">\n    <author id="b796-7">Gardner, J.,'
                "</author>\n    <p>Sample text</p>\n  "
                "</opinion>\n</casebody>\n",
            },
        }

        all_data = fetch_non_harvard_data(case_data)

        self.assertEqual(
            all_data.get("syllabus"), "<p> This is a syllabus " "example.</p>"
        )
        self.assertEqual(all_data.get("judges"), "Broyles, Gardner, MacIntyre")
        self.assertEqual(
            all_data.get("attorneys"),
            "B. B. Giles, for plaintiff in error., Lindley W. Gamp, "
            "solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, "
            "contra.",
        )


class ColumbiaMergerTests(TestCase):
    def setUp(self):
        """Setup columbia merger tests"""
        self.read_xml_to_soup_patch = patch(
            "cl.corpus_importer.management.commands.columbia_merge.read_xml_to_soup"
        )
        self.read_xml_to_soup_func = self.read_xml_to_soup_patch.start()

    def tearDown(self) -> None:
        """Tear down patches and remove added objects"""
        Docket.objects.all().delete()
        self.read_xml_to_soup_patch.stop()

    def test_merger(self):
        """Can we identify opinions correctly even when they are slightly
        different"""

        # Xml content with bad tags </footnote_body></block_quote> instead of
        # </block_quote></footnote_body> and unpublished opinion
        case_xml = """<opinion unpublished=true>
<reporter_caption>
<center>
MENDOZA v. STATE,
<citation>61 S.W.3d 498</citation>
(Tex.App.-San Antonio [4th Dist.] 2001)
</center>
</reporter_caption>
<caption>
<center>PIOQUINTO MENDOZA, III, Appellant, v. THE STATE OF TEXAS, Appellee.</center>
</caption>
<docket>
<center>No. 04-00-00521-CR.</center>
</docket>
<court>
<center>Court of Appeals of Texas, Fourth District, San Antonio.</center>
</court>
<date>
<center>Delivered and Filed: July 25, 2001.</center>
<center>Rehearing Overruled August 21, 2001.</center>
<center>Discretionary Review Granted February 13, 2002.</center>
</date>
<posture>
Appeal from the 49th Judicial District Court, Webb County, Texas, Trial Court No. 99-CRN3-0088-DI, Honorable Manuel Flores, Judge Presiding
<footnote_reference>[fn1]</footnote_reference>
.
<footnote_body>
<footnote_number>[fn1]</footnote_number>
Judge Flores presided over the pre-trial hearings. The Honorable Peter Michael Curry, Visiting Judge, presided over the trial on the merits.
</footnote_body>
<page_number>Page 499</page_number>
</posture>
<opinion_text>
[EDITORS' NOTE: THIS PAGE CONTAINS HEADNOTES. HEADNOTES ARE NOT AN OFFICIAL PRODUCT OF THE COURT, THEREFORE THEY ARE NOT DISPLAYED.]
<page_number>Page 500</page_number>
</opinion_text>
<attorneys> Fernando Sanchez, Law Offices of Fernando Sanchez, Laredo, for appellant. Oscar J. Hale, Assistant District Attorney, Laredo, for appellee. </attorneys>
<panel> Sitting: TOM RICKHOFF, ALMA L. LOPEZ, and SARAH B. DUNCAN, Justices. </panel>
<opinion_byline> Opinion by ALMA L. LOPEZ, Justice. </opinion_byline>
<opinion_text>
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam quis elit sed dui interdum feugiat.
<footnote_body>
<footnote_number>[fn1]</footnote_number>
<block_quote>Footnote sample
</footnote_body></block_quote>
</opinion_text>
</opinion>
        """

        fixed_case_xml = fix_xml_tags(case_xml)

        self.read_xml_to_soup_func.return_value = BeautifulSoup(
            fixed_case_xml, "lxml"
        )

        # Factory create cluster, data from cluster id: 1589121
        cluster = OpinionClusterFactoryMultipleOpinions(
            case_name="Mendoza v. State",
            case_name_full="Pioquinto MENDOZA, III, Appellant, v. the STATE of Texas, "
            "Appellee",
            date_filed=date(2002, 2, 13),
            attorneys="Fernando Sanchez, Law Offices of Fernando Sanchez, Laredo, "
            "for appellant., Oscar J. Hale, Assistant District Attorney, Laredo, "
            "for appellee.",
            other_dates="Rehearing Overruled Aug. 21, 2001., Discretionary Review "
            "Granted Feb. 13, 2002.",
            posture="",
            judges="Alma, Duncan, Lopez, Rickhoff, Sarah, Tom",
            source=SOURCES.LAWBOX_M_HARVARD,
            docket=DocketFactory(source=Docket.HARVARD),
            sub_opinions__data=[
                {
                    "type": "010combined",
                    "xml_harvard": "<p>Lorem ipsum dolor sit amet, consectetur "
                    "adipiscing elit. Nullam quis elit sed dui "
                    "interdum feugiat.</p>",
                    "html_columbia": "",
                    "author_str": "Lopez",
                },
            ],
        )

        # cluster posture is empty
        self.assertEqual(cluster.posture, "")

        # html_columbia is empty
        self.assertEqual(cluster.sub_opinions.all().first().html_columbia, "")

        # Merge cluster
        process_cluster(cluster.id, "/columbia/fake_filepath.xml")

        # Reload the object
        cluster.refresh_from_db()

        # Check if merged metadata is updated correctly
        self.assertEqual(
            cluster.posture,
            "Appeal from the 49th Judicial District Court, Webb County, Texas, "
            "Trial Court No. 99-CRN3-0088-DI, Honorable Manuel Flores, "
            "Judge Presiding [fn1] . [fn1] Judge Flores presided over the pre-trial "
            "hearings. The Honorable Peter Michael Curry, Visiting Judge, presided "
            "over the trial on the merits. Page 499",
        )
        # check if we saved opinion content in html_columbia field
        self.assertEqual(
            cluster.sub_opinions.all().first().html_columbia,
            """<p>[EDITORS' NOTE: THIS PAGE CONTAINS HEADNOTES. HEADNOTES ARE NOT AN OFFICIAL PRODUCT OF THE COURT, THEREFORE THEY ARE NOT DISPLAYED.]
 <span class="star-pagination">*Page 500</span> </p>
<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam quis elit sed dui interdum feugiat.
<footnote_body>
<sup id="op0-fn1"><a href="#op0-ref-fn1">1</a></sup>
<blockquote>Footnote sample
</blockquote></footnote_body></p>""",
        )

        # Ensure the cluster is not merged again if it has already been merged
        # and the COLUMBIA source was assigned.
        with patch(
            "cl.corpus_importer.management.commands.columbia_merge.logger"
        ) as mock_logger:
            # Merge cluster
            process_cluster(cluster.id, "/columbia/fake_filepath.xml")
            mock_logger.info.assert_called_with(
                f"Cluster id: {cluster.id} already merged"
            )


@patch(
    "cl.corpus_importer.tasks.get_or_cache_pacer_cookies",
    return_value=None,
)
class ScrapeIqueryPagesTest(TestCase):
    """Tests related to iquery_pages_probing_daemon command."""

    @classmethod
    def setUpTestData(cls):
        Court.objects.all().delete()
        cls.court_canb = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_cand = CourtFactory(id="cand", jurisdiction="FB")
        cls.court_nysd = CourtFactory(id="nysd", jurisdiction="FB")
        cls.court_gamb = CourtFactory(id="gamb", jurisdiction="FB")
        cls.court_hib = CourtFactory(id="hib", jurisdiction="FB")
        cls.court_gand = CourtFactory(id="gand", jurisdiction="F")

    def setUp(self) -> None:
        self.r = get_redis_interface("CACHE")
        keys_to_clean = [
            "pacer_case_id_final",
            "court_wait:*",
            "court_probe_cycle_no_hits",
            "iquery.probing.enqueued:*",
        ]
        for key_to_clean in keys_to_clean:
            key = self.r.keys(key_to_clean)
            if key:
                self.r.delete(*key)

    def test_compute_next_binary_probe(self, mock_cookies):
        """Confirm the method compute_next_binary_probe generates the expected
        probe pattern based on the initial variables."""

        pacer_case_id_final = 0
        probe_iteration = 0
        court_probe_cycle_no_hits = 1
        probe_limit = 256
        probe_pattern = []
        for i in range(9):
            probe_iteration, next_probe = compute_next_binary_probe(
                pacer_case_id_final,
                probe_iteration,
                court_probe_cycle_no_hits,
                probe_limit,
            )
            probe_pattern.append(next_probe)

        expected_pattern = [1, 2, 4, 8, 16, 32, 64, 128, 256]
        self.assertEqual(
            expected_pattern,
            probe_pattern,
            msg="The probe pattern didn't match",
        )

        # Apply jitter.
        court_probe_cycle_no_hits = 2
        probe_iteration = 0
        probe_pattern_jitter = []
        for i in range(9):
            probe_iteration, next_probe = compute_next_binary_probe(
                pacer_case_id_final,
                probe_iteration,
                court_probe_cycle_no_hits,
                probe_limit,
            )
            probe_pattern_jitter.append(next_probe)

        # Each element of probe_pattern_jitter can't deviate more than 13
        # round(256 * 0.05)
        deviation_threshold = 13
        for expected, actual in zip(expected_pattern, probe_pattern_jitter):
            self.assertTrue(
                abs(expected - actual) <= deviation_threshold,
                msg=f"The value {actual} deviates from {expected} by more than {deviation_threshold}",
            )

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing(self, mock_cookies):
        """Test iquery_pages_probing."""

        dockets = Docket.objects.filter(court_id=self.court_cand.pk)
        self.assertEqual(dockets.count(), 0)
        r = get_redis_interface("CACHE")
        # Simulate a pacer_case_id_final  = 8
        r.hset("pacer_case_id_final", self.court_cand.pk, 8)
        # First court_probe_cycle_no_hits, no jitter
        r.hset("court_probe_cycle_no_hits", self.court_cand.pk, 0)
        # Execute the task
        iquery_pages_probing.delay(self.court_cand.pk)

        # New pacer_case_id_final according to the test pattern in
        # cl.tests.fakes.test_pattern_one
        # {
        #     9: True,
        #     10: False,
        #     12: True,
        #     16: False,
        #     24: True,
        #     40: True,
        #     72: False,
        #     136: False,
        #     264: True,
        # }
        # Note that the probing is aborted on 136 after reaching to False hits
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_cand.pk)
        self.assertEqual(int(pacer_case_id_final), 40)
        # Probing will add 4 more dockets
        self.assertEqual(
            dockets.count(), 4, msg="Docket number doesn't match."
        )

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing_nysd(self, mock_cookies):
        """Test iquery_pages_probing."""

        dockets = Docket.objects.filter(court_id=self.court_nysd.pk)
        self.assertEqual(dockets.count(), 0)
        r = get_redis_interface("CACHE")
        # Simulate a pacer_case_id_final  = 8
        r.hset("pacer_case_id_final", self.court_nysd.pk, 8)
        # First court_probe_cycle_no_hits, no jitter
        r.hset("court_probe_cycle_no_hits", self.court_nysd.pk, 0)
        # Execute the task
        iquery_pages_probing.delay(self.court_nysd.pk)

        # New pacer_case_id_final according to the test pattern in
        # cl.tests.fakes.test_patterns
        # {
        #     9: True,
        #     10: False,
        #     12: True,
        #     16: False,
        #     24: True,
        #     40: True,
        #     72: True,
        #     136: False,
        #     264: True,
        #     520: True,
        # }
        # Note that the probe is terminated on 264 after reaching the 9 probe
        # iterations.
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_nysd.pk)
        self.assertEqual(int(pacer_case_id_final), 264)
        # Probing will add 6 more dockets
        dockets = Docket.objects.filter(
            court_id=self.court_nysd.pk,
            pacer_case_id__in=["9", "12", "24", "40", "72", "264"],
        )
        self.assertEqual(
            dockets.count(), 6, msg="Docket number doesn't match."
        )

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing_court_down(self, mock_cookies):
        """Test a court is down or has blocked us. Abort the scrape and set a
        long wait equals to IQUERY_COURT_BLOCKED_WAIT."""

        r = get_redis_interface("CACHE")
        # Simulate a pacer_case_id_final  = 8
        r.hset("pacer_case_id_final", self.court_gamb.pk, 8)
        # First court_probe_cycle_no_hits, no jitter
        r.hset("court_probe_cycle_no_hits", self.court_gamb.pk, 0)
        # Execute the task
        iquery_pages_probing.delay(self.court_gamb.pk)

        # pacer_case_id_final is not updated due to the block.
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_gamb.pk)
        self.assertEqual(int(pacer_case_id_final), 8)
        # court_wait is set to 2 (IQUERY_COURT_BLOCKED_WAIT)
        court_wait = r.get(f"court_wait:{self.court_gamb.pk}")
        self.assertEqual(int(court_wait), 2)

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing_court_timeout(self, mock_cookies):
        """Test a CaseQuery request times out. Wait IQUERY_COURT_TIMEOUT_WAIT
        seconds before trying the next pacer_case_id."""

        r = get_redis_interface("CACHE")
        # Simulate a pacer_case_id_final  = 8
        r.hset("pacer_case_id_final", self.court_hib.pk, 8)
        # First court_probe_cycle_no_hits, no jitter
        r.hset("court_probe_cycle_no_hits", self.court_hib.pk, 0)
        # Execute the task
        with patch("cl.corpus_importer.tasks.time.sleep") as mock_sleep:
            iquery_pages_probing.delay(self.court_hib.pk)

        # 9 IQUERY_COURT_TIMEOUT_WAIT sleeps before aborting the task.
        # 3 iterations * 3 retries each.
        self.assertEqual(mock_sleep.call_count, 9)
        # pacer_case_id_final is not updated due to the block.
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_hib.pk)
        self.assertEqual(int(pacer_case_id_final), 8)

        # court_wait is set to 2 (IQUERY_COURT_BLOCKED_WAIT)
        court_wait = r.get(f"court_wait:{self.court_hib.pk}")
        self.assertEqual(int(court_wait), 2)

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing_daemon(self, mock_cookies):
        """Test iquery_pages_probing_daemon by providing an initial and final
        pacer_case_ids to scrape."""

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 0)
        r = get_redis_interface("CACHE")
        r.hset("pacer_case_id_final", self.court_canb.pk, 0)
        r.hset("pacer_case_id_final", self.court_cand.pk, 135)

        r.hset("pacer_case_id_final", self.court_nysd.pk, 1000)
        r.hset("pacer_case_id_final", self.court_gamb.pk, 1000)
        r.hset("pacer_case_id_final", self.court_hib.pk, 1000)
        r.hset("pacer_case_id_final", self.court_gand.pk, 1000)

        with patch("cl.corpus_importer.tasks.time.sleep") as mock_sleep:
            call_command(
                "iquery_pages_probing_daemon",
                testing_iterations=1,
            )
        # 3 additional dockets should exist after complete the probe.
        # 2 for canb and 1 for cand
        self.assertEqual(
            dockets.count(), 3, msg="Docket number doesn't match."
        )

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_iquery_pages_probing_daemon_court_down_and_timeout(
        self, mock_cookies
    ):
        """Test iquery_pages_probing_daemon when a court has blocked us or
        is the requests are timing out.
        """

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 0)
        r = get_redis_interface("CACHE")
        r.hset("pacer_case_id_final", self.court_gamb.pk, 8)
        r.hset("pacer_case_id_final", self.court_hib.pk, 8)

        court_wait_gamb = r.get(f"court_wait:{self.court_gamb.pk}")
        self.assertEqual(court_wait_gamb, None)
        court_wait_hib = r.get(f"court_wait:{self.court_hib.pk}")
        self.assertEqual(court_wait_hib, None)

        # Set a high pacer_case_id_final that's outside
        # cl.tests.fakes.test_patterns, so they are aborted.
        r.hset("pacer_case_id_final", self.court_cand.pk, 1000)
        r.hset("pacer_case_id_final", self.court_nysd.pk, 1000)
        r.hset("pacer_case_id_final", self.court_canb.pk, 1000)
        r.hset("pacer_case_id_final", self.court_gand.pk, 1000)

        with patch("cl.corpus_importer.tasks.time.sleep") as mock_sleep:
            call_command(
                "iquery_pages_probing_daemon",
                testing_iterations=1,
            )

        # Assertions for court_gamb blocked.
        # pacer_case_id_final is not updated due to court_gamb block.
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_gamb.pk)
        self.assertEqual(int(pacer_case_id_final), 8)
        # court_wait is set to 2 (IQUERY_COURT_BLOCKED_WAIT)
        court_wait = r.get(f"court_wait:{self.court_gamb.pk}")
        self.assertEqual(int(court_wait), 2)

        # Assertions for court_hib timeouts.
        # 9 IQUERY_COURT_TIMEOUT_WAIT sleeps before aborting the task.
        # 3 iterations * 3 retries each.
        self.assertEqual(mock_sleep.call_count, 9)
        # pacer_case_id_final is not updated due to the block.
        pacer_case_id_final = r.hget("pacer_case_id_final", self.court_hib.pk)
        self.assertEqual(int(pacer_case_id_final), 8)
        # court_wait is set to 2 (IQUERY_COURT_BLOCKED_WAIT)
        court_wait = r.get(f"court_wait:{self.court_hib.pk}")
        self.assertEqual(int(court_wait), 2)

    @patch(
        "cl.corpus_importer.tasks.CaseQuery",
        new=FakeCaseQueryReport,
    )
    def test_update_latest_case_id_and_schedule_iquery_sweep_task(
        self, mock_cookies
    ):
        """Test if the latest pacer_case_id is kept up to date upon docket
        creation and if the iquery retrieval is performed properly.
        """
        # Connect handle_update_latest_case_id_and_schedule_iquery_sweep signal
        # with a unique dispatch_uid for this test
        test_dispatch_uid = (
            "test_handle_update_latest_case_id_and_schedule_iquery_sweep"
        )
        post_save.connect(
            handle_update_latest_case_id_and_schedule_iquery_sweep,
            sender=Docket,
            dispatch_uid=test_dispatch_uid,
        )
        try:
            dockets = Docket.objects.filter(court_id=self.court_gand)
            self.assertEqual(dockets.count(), 0)

            r = get_redis_interface("CACHE")
            # Simulate a pacer_case_id_final = 5
            r.hset("pacer_case_id_final", self.court_gand.pk, 5)

            # Create a Docket with a pacer_case_id smaller than pacer_case_id_final
            with patch(
                "cl.corpus_importer.signals.update_latest_case_id_and_schedule_iquery_sweep",
                side_effect=lambda *args, **kwargs: update_latest_case_id_and_schedule_iquery_sweep(
                    *args, **kwargs
                ),
            ) as mock_iquery_sweep, self.captureOnCommitCallbacks(
                execute=True
            ):
                DocketFactory(
                    court=self.court_gand,
                    source=Docket.RECAP,
                    docket_number="2:20-cv-00600",
                    pacer_case_id="4",
                )

            # update_latest_case_id_and_schedule_iquery_sweep should be called 1 time
            self.assertEqual(mock_iquery_sweep.call_count, 1)

            # pacer_case_id_final shouldn't have changed.
            pacer_case_id_final = r.hget(
                "pacer_case_id_final", self.court_gand.pk
            )
            self.assertEqual(int(pacer_case_id_final), 5)
            self.assertEqual(dockets.count(), 1)

            # Create a Docket with a pacer_case_id bigger than pacer_case_id_final
            with patch(
                "cl.corpus_importer.signals.update_latest_case_id_and_schedule_iquery_sweep",
                side_effect=lambda *args, **kwargs: update_latest_case_id_and_schedule_iquery_sweep(
                    *args, **kwargs
                ),
            ) as mock_iquery_sweep, self.captureOnCommitCallbacks(
                execute=True
            ):
                DocketFactory(
                    court=self.court_gand,
                    source=Docket.RECAP,
                    case_name="New Incoming Docket",
                    docket_number="2:20-cv-00601",
                    pacer_case_id="8",
                )

            # update_latest_case_id_and_schedule_iquery_sweep should be called once.
            # The 2 dockets retrieved by the iquery sweep shouldn't call
            # update_latest_case_id_and_schedule_iquery_sweep.
            self.assertEqual(mock_iquery_sweep.call_count, 1)

            # Two dockets should have been created.
            self.assertEqual(dockets.count(), 4)
            pacer_case_id_final = r.hget(
                "pacer_case_id_final", self.court_gand.pk
            )
            self.assertEqual(int(pacer_case_id_final), 8)

            # Create a RECAP docket with no pacer_case_id, it should be ignored
            with patch(
                "cl.corpus_importer.signals.update_latest_case_id_and_schedule_iquery_sweep",
                side_effect=lambda *args, **kwargs: update_latest_case_id_and_schedule_iquery_sweep(
                    *args, **kwargs
                ),
            ) as mock_iquery_sweep, self.captureOnCommitCallbacks(
                execute=True
            ):
                DocketFactory(
                    court=self.court_gand,
                    source=Docket.RECAP,
                    docket_number="2:20-cv-00602",
                    pacer_case_id=None,
                )

            # One extra docket created by the factory.
            self.assertEqual(dockets.count(), 5)
            pacer_case_id_final = r.hget(
                "pacer_case_id_final", self.court_gand.pk
            )
            # pacer_case_id_final should remain the same.
            self.assertEqual(int(pacer_case_id_final), 8)

        finally:
            # Ensure the signal is disconnected after the test
            post_save.disconnect(
                handle_update_latest_case_id_and_schedule_iquery_sweep,
                sender=Docket,
                dispatch_uid=test_dispatch_uid,
            )
