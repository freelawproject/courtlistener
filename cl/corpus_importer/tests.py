import json
from datetime import date, datetime
from unittest.mock import patch

import eyecite
import pytest
from factory import RelatedFactory

from cl.corpus_importer.court_regexes import match_court_string
from cl.corpus_importer.factories import (
    CaseBodyFactory,
    CaseLawCourtFactory,
    CaseLawFactory,
    CitationFactory,
)
from cl.corpus_importer.import_columbia.parse_opinions import (
    get_state_court_object,
)
from cl.corpus_importer.management.commands.harvard_merge import (
    combine_non_overlapping_data,
    merge_docket_numbers,
    merge_judges,
    merge_opinion_clusters,
)
from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_body_content,
    compare_documents,
    parse_harvard_opinions,
    validate_dt,
    winnow_case_name,
)
from cl.corpus_importer.management.commands.normalize_judges_opinions import (
    normalize_authors_in_opinions,
    normalize_panel_in_opinioncluster,
)
from cl.corpus_importer.tasks import generate_ia_json
from cl.corpus_importer.utils import get_start_of_quarter
from cl.lib.pacer import process_docket_data
from cl.people_db.factories import PersonWithChildrenFactory, PositionFactory
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.models import UPLOAD_TYPE
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterFactoryMultipleOpinions,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionClusterWithParentsFactory,
    OpinionFactory,
    OpinionWithChildrenFactory,
)
from cl.search.models import (
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


class HarvardMergerTests(TestCase):
    def setUp(self):
        """Setup harvard tests

        This setup is a little distinct from normal ones.  Here we are actually
        setting up our patches which are used by the majority of the tests.
        Each one can be used or turned off.  See the teardown for more.
        :return:
        """
        self.read_json_patch = patch(
            "cl.corpus_importer.management.commands.harvard_merge.read_json"
        )
        self.read_json_func = self.read_json_patch.start()

    def tearDown(self) -> None:
        """Tear down patches and remove added objects"""
        Docket.objects.all().delete()
        self.read_json_patch.stop()

    def test_merger(self):
        """Can we identify opinions correctly even when they are slightly different."""

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
            docket=DocketFactory(),
            sub_opinions__data=[
                {"type": "020lead", "html_with_citations": lead},
                {"type": "030concurrence", "html_with_citations": concurrence},
            ],
        )

        self.assertEqual(
            OpinionCluster.objects.get(id=cluster.id).attorneys, "", msg="WHAT"
        )

        self.assertEqual(Opinion.objects.all().count(), 2)
        merge_opinion_clusters(cluster_id=cluster.id)
        self.assertEqual(Opinion.objects.all().count(), 2)

    def test_non_overlapping(self):
        """Can we find fields that need merging"""

        case_data = {
            "casebody": {
                "status": "ok",
                "data": '<casebody> <attorneys><page-number citation-index="1" label="758">*758</page-number><em>B. B. Giles, </em>for plaintiff in error.</attorneys>\n  <attorneys id="b796-5"><em>Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, </em>contra.</attorneys>\n  <opinion type="majority"> a simple opinion</opinion>\n</casebody>\n',
            },
        }
        self.read_json_func.return_value = case_data

        cluster = OpinionClusterFactoryMultipleOpinions(
            docket=DocketFactory(),
            attorneys="B. B. Giles, Lindley W. Gamp, and John A. Boyhin",
            # cl value
        )
        clean_dictionary = combine_non_overlapping_data(cluster.id, case_data)
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
        clean_dictionary = combine_non_overlapping_data(cluster.id, case_data)
        self.assertEqual(clean_dictionary, {}, msg="Attorneys are the same")

    def test_docket_number_merger(self):
        """Can we choose the correct docket number"""
        docket = DocketFactory(docket_number="17-3000")
        cluster = OpinionClusterWithParentsFactory(docket=docket)
        merge_docket_numbers(cluster.id, "Master Docket No. 17-3000L")
        docket.refresh_from_db()
        self.assertEqual(docket.docket_number, "Master Docket No. 17-3000L")

    def test_merge_overlap_judges(self):
        """Test merge judge names when overlap exist"""

        # Test 1: Example from CL #4575556
        cluster = OpinionClusterWithParentsFactory(
            judges="Barbera",
        )
        # clean_dictionary after preprocess {"judges":(harvard_data, cl_data)}
        cd = {
            "judges": (
                "Adkins, Barbera, Getty, Greene, Hotten, McDonald, Watts",
                "Barbera",
            )
        }

        # Original value from harvard case without preprocess
        raw_judges_harvard = (
            "Argued before Barbera, C.J., Greene,* Adkins, "
            "McDonald, Watts, Hotten, Getty, JJ. "
        )

        merge_judges(
            cluster.pk, "judges", cd.get("judges"), raw_judges_harvard
        )
        cluster.refresh_from_db()

        # Test best option selected for judges is in harvard data
        self.assertEqual(
            cluster.judges,
            "Adkins, Barbera, Getty, Greene, Hotten, McDonald, Watts",
        )

        # Test 2: Example from CL #4573873
        cluster_2 = OpinionClusterWithParentsFactory(
            judges="Simpson, J. ~ Concurring Opinion by Pellegrini, Senior Judge",
        )

        # preprocessed values {"judges":(harvard_data, cl_data)}
        cd = {
            "judges": (
                "Simpson",
                "Pellegrini, Simpson",
            )
        }

        # Original value from harvard case without preprocess
        raw_judges_harvard = "OPINION BY JUDGE SIMPSON"

        merge_judges(
            cluster_2.pk, "judges", cd.get("judges"), raw_judges_harvard
        )
        cluster_2.refresh_from_db()

        # Best option selected for judges is already in cl
        self.assertEqual(
            cluster_2.judges,
            "Simpson, J. ~ Concurring Opinion by Pellegrini, Senior Judge",
        )

        # Test 3: Example from CL #4576003
        cluster_3 = OpinionClusterWithParentsFactory(
            judges="French, J.",
        )

        # preprocessed values {"judges":(harvard_data, cl_data)}
        cd = {
            "judges": (
                "Fischer, French, Kennedy",
                "French, J.",
            )
        }

        # Original value from harvard case without preprocess
        raw_judges_harvard = (
            "Fischer, J., dissenting., French, J., Kennedy, J., dissenting."
        )

        merge_judges(
            cluster_3.pk, "judges", cd.get("judges"), raw_judges_harvard
        )
        cluster_3.refresh_from_db()

        # Test best option selected for judges is in harvard data
        self.assertEqual(cluster_3.judges, "Fischer, French, Kennedy")

        # Test 4: Example from CL #4571591
        cluster_4 = OpinionClusterWithParentsFactory(
            judges="Leavitt, President Judge",
        )

        # preprocessed values {"judges":(harvard_data, cl_data)}
        cd = {
            "judges": (
                "Leavitt",
                "Leavitt",
            )
        }

        # Original value from harvard case without preprocess
        raw_judges_harvard = "OPINION BY PRESIDENT JUDGE LEAVITT"

        merge_judges(
            cluster_4.pk, "judges", cd.get("judges"), raw_judges_harvard
        )
        cluster_4.refresh_from_db()

        # Test best option selected for judges is in harvard data
        self.assertEqual(
            cluster_4.judges, "Opinion by President Judge Leavitt"
        )

    # class HarvardMergerTests(TestCase):
    #     def setUp(self):
    #         """Setup harvard tests
    #
    #         This setup is a little distinct from normal ones.  Here we are actually
    #         setting up our patches which are used by the majority of the tests.
    #         Each one can be used or turned off.  See the teardown for more.
    #         :return:
    #         """
    #         self.read_json_patch = patch(
    #             "cl.corpus_importer.management.commands.harvard_merge.read_json"
    #         )
    #         self.read_json_func = self.read_json_patch.start()
    #
    #     def tearDown(self) -> None:
    #         """Tear down patches and remove added objects"""
    #         # Docket.objects.all().delete()
    #         self.read_json_patch.stop()
    #
    #     def test_merge_opinions(self):
    #         harvard_data = {
    #             "casebody": {
    #                 # "data": "<?xml version='1.0' encoding='utf-8'?>\n<casebody xmlns=\"http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" firstpage=\"279\" lastpage=\"293\"><docketnumber id=\"b279-3\" pgmap=\"279\">(No. 23002.</docketnumber><parties id=\"b279-4\" pgmap=\"279\">Henry R. Levy, Appellant, vs. The Broadway-Carmen Building Corporation, Appellee.</parties><decisiondate id=\"b279-5\" pgmap=\"279\">Opinion filed April 16, 1937.</decisiondate><p id=\"b280-3\" pgmap=\"280\">Stone and Shaw, JJ., specially concurring.</p><p id=\"b280-4\" pgmap=\"280\">Herrick, C. J., and Orr, J., dissenting.</p><attorneys id=\"b280-6\" pgmap=\"280\">Isaac B. Lipson, (A. C. Lewis, of counsel,) for appellant.</attorneys><attorneys id=\"b280-7\" pgmap=\"280\">Kamfner, Halligan &amp; Marks, (Samuer M. Lanoff, of counsel,) for appellee.</attorneys> <opinion type=\"majority\"> <author id=\"b280-8\" pgmap=\"280\">Mr. Justice Farthing</author> <p id=\"ADb\" pgmap=\"280\">delivered the opinion of the court:</p> <p id=\"b280-9\" pgmap=\"280(154) 281(364) 282(102)\">Henry R. Levy, the appellant, was the principal stockholder in the Studebaker Sales Company of Chicago. In January, 1926, David Gordon purchased the land involved in this foreclosure, from that company. He paid $35,000, in cash, and secured the balance of $100,000 by a mortgage. He reduced the debt to $70,000, and on April 13, 1931, when this became due, an agreement was made between Gordon and Levy by which $5000 more was paid and the property was deeded to the Broadway-Carmen Building Corporation, organized by Gordon. That company gave its note for $65,000, guaranteed by Gordon and his wife, and secured by a trust deed on the premises. In addition, Levy received a commission of \" $1950. After $2500 had been paid on the principal debt, default was made by the mortgagor, and Levy obtained a judgment at law against David Gordon and Ida Gordon, his wife, for $66,691.87. He also brought this suit to foreclose the trust deed. The superior court of Cook county rendered a decree on May 26, 1933) and found that $70,246.91 was due Levy on March 15, 1933. It ordered the mortgaged premises sold at public auction and directed the master in chancery to carry out the decree. Accordingly the master, on June 21, 1933, struck off the property to appellant, Levy, for $50,000. The appellee filed objections to the report of sale. It claimed that the property was reasonably worth $80,000, but that economic conditions had resulted in the destruction of the market for real estate in Chicago. It prayed that the court establish the value of the premises and credit that value on the amount found due Levy; that a deficiency judgment be denied and that the judgment previously rendered against Gordon and wife, be satisfied in full. It stated that it had offered, and was then willing, to deed the property to the appellant in cancellation of the debt. Levy answered, denying that the premises were worth more than $50,000. He set up the fact that the property was being managed by a receiver and that the rental was $150 per month, plus $5 for each automobile sold by the lessee; that the 1929, 1930 and 1931 taxes, totalling $6000, were unpaid. He offered to assign his certificate of purchase to anyone for the amount of his bid. The mortgaged premises are located at a street intersection and are known as No. 5100 Broadway. The lot is 97 by 100 feet and is improved with a one-story automobile display building and service garage. Both parties introduced affidavits as to value. Those on behalf of appellee, set the value at $77,400 to $80,000, which was based on a rental value of $400 per month, and a possible rental of $500 if the building were divided into storerooms. The affidavits on behalf of appellant showed that the improvements cost $35,902 thirteen years before, and that their replacement value was $22,500. They showed the reasonable rental value to be $250 per month and fixed the value of the premises at from $40,000 to $50,000. At the close of the hearing on the objections, the chancellor ordered that the sale be approved, provided the appellant released and cancelled the outstanding judgment against the Gordons, and the mortgage indebtedness, but Levy refused to do this. A decree was entered on January 20, 1934, denying confirmation of the master’s report of sale. It ordered a re-sale of the property at an upset price of $71,508.45, the amount then due, together with interest and costs of suit. The Appellate Court for the First District affirmed this decree on appeal. We granted leave and the cause is here on appeal.</p> <p id=\"b282-3\" pgmap=\"282\">Appellant contends that the order of January 20, 1934, denying confirmation of the master’s report and directing a new sale at an upset price, was an amendment to the foreclosure decree dated May 26, 1933, and that the later decree was of no effect, because'it was rendered at a succeeding term. This contention cannot be upheld. It was the duty of the court to supervise the sale and to approve or reject the report. If rejected, it was the duty of the court to order a re-sale and directions as to time, place and terms of sale were but incidents to such order. Mariner v. Ingraham, 230 Ill. 130; L. R A. 1915A, 699.</p> <p id=\"b282-4\" pgmap=\"282(145) 283(382) 284(21)\">As stated by appellant the remaining points for consideration are embodied in the question: May the chancellor, in a suit to foreclose a real estate mortgage, require the plaintiff to waive his right to a deficiency decree as a condition precedent to confirming the master’s report of sale, or, in the alternative, may the chancellor fix a value ■ and direct the master not to accept a bid lower than this reserved or upset price? Appellant says a court of equity is without power to disapprove a master’s report of sale in a foreclosure suit, except there be mistake, fraud or some violation of duty by the purchaser or the master. He says that no matter how grossly inadequate the bid may be, it does not constitute fraud, or warrant the chancellor in disapproving the sale. No argument is required to disclose or sustain the wisdom of the rule that public policy and the interest of debtors require stability in judicial sales and that these sales should not be disturbed without cause. However, it is to be observed that the rule requiring more than mere inadequacy of price, and the showing of a breach of duty by the purchaser or the officer, or a fraud upon the debtor, arose out of cases where the judicial sales had been consummated and not out of mere offers to buy from a court. For example in Skakel v. Cycle Trade Publishing Co. 237 Ill. 482, the complainant brought his action to set aside a sheriff’s sale and a deed already executed. The cases of Mixer v. Sibley, 53 Ill. 61, Davis v. Pickett, 72 id. 483, O’Callaghan v. O’Callaghan, 91 id. 228, and Smith v. Huntoon, 134 id. 24, all involved sales under executions at law. Dobbins v. Wilson, 107 Ill. 17, concerned a deed issued following a United States marshal’s sale. Quigley v. Breckenridge, 180 Ill. 627, involved a sale made pursuant to a decree for partition, and although we held that the sale was fair and the master’s report.of sale should have been approved, nevertheless we re-affirmed the doctrine that a court of chancery possesses a large discretion in passing upon masters’ reports of sale. In that case we pointed out the fact that such a sale is not completed until it is confirmed, and that until then, it confers no right in the land upon the purchaser. The sale in Bondurant v. Bondurant, 251 Ill. 324, was made by a trustee who had power to sell the land at public vendue and was not a judicial sale in the legal sense. In the case of Allen v. Shepard, 87 Ill. 314, we exercised our judicial power to determine whether or not the bid made at an administrator’s sale was adequate, and determined that it was. In Clegg v. Christensen, 346 Ill. 314, we again exercised the same power. Abbott v. Beebe, 226 Ill. 417, concerned a partition sale. The land brought more than two-thirds of the appraised value. We again declared that there was power in the chancellor to set aside a judicial sale for inadequacy of price but we held that the- facts showed the sale under consideration was fairly made. The record did not disclose any inadequacy in the price.</p> <p id=\"b284-3\" pgmap=\"284\">In sales by conservators, guardians and trustees, involving consideration of objections filed before reports of sale were approved, inadequacy of price has always been considered in determining whether the sale was fairly made and whether the report should be approved and confirmed. In most of the cases the objector tendered a larger bid and very often the bid was required to be secured, but the fact that there ,was such an increased bid was, at most, evidence that the sale price was inadequate. In Kloepping v. Stellmacher, 21 N. J. Eq. 328, a sheriff sold property worth $2000 for $52. The owner was ignorant, stupid and perverse, and would not believe his property would be sold for so trifling an amount, although he had been forewarned. Redemption was allowed upon payment of the purchase price and costs. The court said: “But when such gross inadequacy is combined with fraud or mistake, or any other ground of relief in equity, it will incline the court strongly to afford relief. The sale in this case is a great oppression on the complainants. They are ignorant, stupid, perverse and poor. They lose by it all their property, and are ill fitted to acquire more. They are such as this court should incline to protect, notwithstanding perverseness.”</p> <p id=\"b284-4\" pgmap=\"284(111) 285(146)\">In Graffam v. Burgess, 117 U. S. 180, 29 L. ed. 839, the Supreme Court of the United States, speaking through Mr. Justice Bradley, said: “It was formerly the rule in England, in chancery sales, that until confirmation of the master’s report, the bidding would be opened upon a mere offer to advance the price 10 per centum. (2 Daniell, Ch. Pr. 1st ed. 924; 2d ed. by Perkins, 1465, 1467; Sugden, V. &amp; P. 14th ed. 114.) But Lord Eldon expressed much dissatisfaction with this practice of opening biddings upon a mere offer of an advanced price, as tending to diminish confidence in such sales, to keep bidders from attending, and to diminish the amount realized. (White v. Wilson, 14 Ves. 151; Williams v. Attleborough, Tur. &amp; Rus. 76; White v. Damon, 7 Ves. 34.) Lord Eldon’s views were finally adopted in England in the Sale of Land by Auction act, 1857, (30 and 31 Victoria, chap. 48, sec. 7,) so that now the highest bidder at a sale by auction of land, under an order of the court, provided he has'bid a sum equal to or higher than the reserved price (if any), will be declared and allowed the purchaser, unless the court or judge, on the ground of fraud or improper conduct in the management of the sale, upon the application of any person interested in the land, either opens the bidding or orders the property to be resold. 1 Sugden, V. &amp; P. 14th ed. by Perkins, 14 note (a).</p> <p id=\"b285-3\" pgmap=\"285\">“In this country Lord Eldon’s views were adopted at an early day by the courts; and the rule has become almost universal that a sale will not be set aside for inadequacy of price unless the inadequacy be so great as to shock the conscience, or unless there be additional circumstances against its fairness; being very much the rule that always prevailed in England as to setting aside sales after the master’s report had been confirmed. [Citing many cases.]</p> <p id=\"b285-4\" pgmap=\"285\">“From the cases here cited we may draw the general conclusion that if the inadequacy of price is so gross as to shock the conscience, or if in addition to gross inadequacy, the purchaser has been guilty of any unfairness, or has taken any undue advantage, or if the owner of the property, or party interested in it, has been for any other reason, misled or surprised, then the sale will be regarded as fraudulent and void, or the party injured will be permitted to redeem the property sold. Great inadequacy requires only slight circumstances of unfairness in the conduct of the party benefited by the sale to raise the presumption of fraud.”</p> <p id=\"b285-5\" pgmap=\"285(22) 286(22)\">In Pewabic Mining Co. v. Mason, 145 U. S. 349, 36 L. ed. 732, Mr. Justice Brewer said, at page 367: “Indeed even before confirmation the sale would not be set aside for mere inadequacy, unless so great as to shock the conscience.”</p> <p id=\"b286-3\" pgmap=\"286\">Stability must be given to judicial sales which have reached the point where title has vested in the purchaser, otherwise bidding would be discouraged. But where a bidder does not become vested with any interest in the land but has only made an offer to buy, subject to the approval of his offer by the court, and he bids with that condition, there can be no good reason why bidding would be discouraged by reason of the court’s power to approve or disapprove the sale for gross inadequacy of bid. Sales by masters are not sales in a legal sense, until they are confirmed. Until then, they are sales only in a popular sense. The accepted bidder acquires no independent right to'have his purchase completed, but remains only a preferred proposer until confirmation of the sale by the court, as agreed to by its ministerial agent. Confirmation is final consent, and the court, being in fact the vendor, may consent or not, in its discretion. (Hart v. Burch, 130 Ill. 426; Jennings v. Dunphy, 174 id. 86; Pewabic Mining Co. v. Mason, supra; Smith v. Arnold, 5 Mason, 414.) In the case last •cited, Mr. Justice Story said, at page 420: “In sales directed by the court of chancery, the whole business is transacted by a public officer, under the guidance and superintendence of the court itself. Even after the sale is made, it is not final until a report is made to the court and it is approved and confirmed.”</p> <p id=\"b286-4\" pgmap=\"286(86) 287(251)\">Many of the decisions, relied upon and cited by appel- . lant, arose out of sales of lands under mortgages or trust deeds which contained a power of sale and were made at a time when there was no redemption, unless it was provided for in the mortgage or trust deed. Such sales were not subject to approval or disapproval by courts and the only remedy the mortgagor had against fraud or other misconduct was by a bill in equity to set aside the conveyanee, or for redemption. In 1843 the legislature passed an act regulating the foreclosure of mortgages on real property which created a redemption period in favor of mortgagors, but the act did not purport to govern trust deeds containing a power of sale. Thereafter the foreclosing of mortgages was committed to courts of chancery, under their general equity powers, except as to certain prescribed matters of procedure. From that time mortgage foreclosure sales were made by an officer who was required to report the sale to the court. Purchasers did not become vested with any interest in the land sold until the report of sale was approved. The court fixed the terms and conditions of foreclosure sales and this practice still continues. In 1879 the legislature provided that no real estate should be sold by virtue of any power of sale contained in any mortgage, trust deed, or other conveyance in the nature of a mortgage, but that thereafter such real estate should be sold in the same manner provided for foreclosure of mortgages containing no power of sale, and then only in pursuance of a judgment or decree of a court of competent jurisdiction. (State Bar Stat. 1935, chap. 95, par. 24; 95 S. H. A. 23.) The history of this legislation is conclusive proof that it was the legislative intent that foreclosure sales should be made only upon such terms and conditions as were approved by the courts. Garrett v. Moss, 20 Ill. 549.</p> <p id=\"b287-3\" pgmap=\"287(103) 288(66)\">Unfairness from any cause which operates to the prejudice of an interested party, will abundantly justify a chancery court in refusing to approve a sale. We said in Roberts v. Goodin, 288 Ill. 561: “The setting aside of the sale and ordering the property re-sold was a matter which rested largely within the discretion of the chancellor, whose duty it was to see that the lien be enforced with the least damage possible to the property rights of the mortgagor. Counsel cite numerous cases touching their contention that the chancellor erred in setting aside this sale. The cases cited, however, arose after the sale had once been confirmed, and not where, as here, the objection to the confirmation of the sale was filed immediately after the sale and before any confirmation had taken place. The chancellor has a broad discretion in the matter of approving or disapproving a master’s sale made subject to the court’s approval by the terms of the decree.”</p> <p id=\"b288-3\" pgmap=\"288\">The legislature’s purpose would be defeated if any other interpretation were given to the statutes on the subject of mortgage foreclosure. It is unusual for land to bring its full, fair market value at a forced sale. While courts can not guarantee that mortgaged property will bring its full value, they can prevent unwarranted sacrifice of a debtor’s property. Mortgage creditors resort to courts of equity for relief and those courts prescribe equitable terms upon which they may receive that relief, and it is within their power to prevent creditors from taking undue and unconscionable advantage of debtors, under the guise of collecting a debt. A slight inadequacy is not sufficient reason to disapprove a master’s sale, but where the amount bid is so grossly inadequate that it shocks the conscience of a court of equity, it is the chancellor’s duty to disapprove the report of sale. Connely v. Rue, 148 Ill. 207; Kiebel v. Reick, 216 id. 474; Wilson v. Ford, 190 id. 614; Ballentyne v. Smith, 205 U. S. 285, 51 L. ed. 803.</p> <p id=\"b288-4\" pgmap=\"288(113) 289(137)\">The case of Slack v. Cooper, 219 Ill. 138, illustrates the rule. In that case the master sold the land, upon which the mortgage had been foreclosed, to the solicitor for the mortgagor for $3000. He acted under the mistaken impression that the buyer was the solicitor for the mortgagee, who appeared shortly thereafter and bid $7000. The master then announced publicly that since no cash had been deposited by the original bidder, and because of the misapprehension stated and his haste in making the sale, it would be re-opened for higher and better bids. At page 144 of that decision we said: “If the chancellor finds upon the coming in of the report of a master, that the sale as made is not to the best interest of all concerned and is inequitable, or that any fraud or misconduct has been practiced upon the master or the court or any irregularities in the proceedings, it is his duty to set aside the sale as made and order another sale of the premises. The chancellor has a broad discretion in passing upon the acts of the master and approving or disapproving his acts in reference to sales and entering his own decrees, (Quigley v. Breckenridge, 180 Ill. 627,) and his decree will not be disturbed by this court unless it is shown that he has abused his discretion and entered such an order or decree as would not seem equitable between the parties interested.”</p> <p id=\"b289-3\" pgmap=\"289\">We have limited our discussion to the power of a court of chancery to approve or disapprove a master’s report of sale in a foreclosure suit and we hold that the court has broad discretionary powers over such sales. Where it appears that the bid offered the court for the premises is so grossly inadequate that its acceptance amounts to a fraud, the court has the power to reject the bid and order a re-sale.</p> <p id=\"b289-4\" pgmap=\"289(159) 290(95)\">There is little or no difference between the equitable jurisdiction' and power in a chancery court to refuse approval to a report of sale on foreclosure, and the power to fix, in advance, a reserved or upset price, as a minimum at which the property may be sold. We have referred to the acts of 1843 and 1879 which require trust deeds and mortgages to be foreclosed in chancery courts and have pointed out that courts of equity, exercising their general equity powers in such cases, have the right to fix reasonable terms and conditions for the carrying out of the provisions of the foreclosure decree, and that such courts may order a new sale and set the old aside for the violation of some duty by the master, or for fraud or mistake. No reason appears why the chancellor cannot prevent a sale at a grossly inadequate price by fixing á reasonable sale price in advance. The same judicial power 'is involved in either action. What is necessary to be done in the end, to prevent fraud and injustice, may be forestalled by proper judicial action in the beginning. Such a course is not against the policy of the law in this State and it is not the equivalent of an appraisal statute. It is common practice in both the State and Federal courts to fix an upset price in mortgage foreclosure suits. This is in harmony with the accepted principles governing judicial power in mortgage foreclosures.</p> <p id=\"b290-3\" pgmap=\"290\">In First National Bank v. Bryn Mawr Beach Building Corp. 365 Ill. 409, we pointed out the fact that such property as was there under consideration seldom sells at anything like its reproduction cost, or even its fair cash market value, at a judicial sale. We recognized the fact that the equity powers of State courts are no more limited than those of Federal courts, and that equity jurisdiction over mortgage foreclosures is general rather than limited or statutory. In part we said: “It would seem that since equity courts have always exercised jurisdiction to decree the enforcement of mortgage liens and to supervise foreclosure sales, such jurisdiction need not expire merely because the questions or conditions surrounding the exercise of such time-honored functions are new or complicated. If it may reasonably be seen that the exercise of the jurisdiction of a court of equity beyond the sale of the property will result in better protection to parties before it, it would seem not only to be germane to matters of undisputed jurisdiction, but to make for the highest exercise of the court’s admitted functions.” We there held that a court of equity has jurisdiction, in connection with an application for approval of a foreclosure sale, to approve a re-organization plan submitted by a bondholders’ committee. The question is somewhat different from that presented in the case before us, but we there recognized the continuing vitality and growth of equity jurisprudence.</p> <p id=\"b291-2\" pgmap=\"291\">Cases wherein an upset price has been fixed are not confined to large properties for which, by reason of their great value, the market is limited or there is no market whatever. In McClintic-Marshall Co. v. Scandinavian-American Building Co. 296 Fed. 601, a building was constructed on two lots covered by the mortgage, and one lot belonging to the mortgagor that was not mortgaged. It was necessary, under the circumstances, to sell all the property, and to protect the mortgagor a reserved price was fixed. The fact of an upset price is referred to, although there was no objection to it being fixed, in Northern Pacific Railway Co. v. Boyd, 228 U. S. 482, 57 L. ed. 931, and Pewabic Mining Co. v. Mason, supra, and the power has been exercised in numerous other cases. 104 A. L. R. 375; 90 id. 1321; 88 id. 1481.</p> <p id=\"b291-3\" pgmap=\"291\">The appellant did not raise constitutional objections in the trial court and by appealing to the Appellate Court for the First District he would waive such questions. However, the fixing of an upset price does not violate section 10 of article 1 of the Federal constitution nor section 14 of article 2 of the Illinois constitution, which inhibit the impairment of the obligation of contracts. The reserved price dealt only with the remedy, and it was within the court’s power to establish it as one of the terms and conditions of the sale. The appellant was not deprived of his right to enforce the contract, and his remedy was neither denied, nor so embarrassed, as to seriously impair the value of his contract or the right to enforce it. Penniman’s Case, 103 U. S. 714, 26 L. ed. 502; Town of Cheney’s Grove v. Van Scoyoc, 357 Ill. 52.</p> <p id=\"b291-4\" pgmap=\"291\">It is contended that the present holding conflicts with what we said in Chicago Title and Trust Co. v. Robin, 361 Ill. 261. It was not necessary to that decision to pass upon the power to fix an upset price, and what we said on that subject is not adhered to.</p> <p id=\"b292-2\" pgmap=\"292\">Each case must be based upon its own facts, and from this record we are of the opinion that no such gross inadequacy existed in the bid of $50,000, as would warrant the chancellor in refusing approval of the master’s sale. Although the rents were pledged in the trust deed, they would amount to but little more than the taxes on the property of approximately $2000 per annum. Appellee’s affidavits base the estimate of value largely on the rental value of the premises. They were rented for $150 per month, plus $5 for each automobile sold by the lessee, and this amounted to a total of $200 a month. Even if the premises brought $400, or the $500 per month which appellee’s witnesses said could be had if the property was divided into storerooms, the cost of these changes is not given. This testimony did not warrant the chancellor in finding that these premises were worth $80,000. Although the property had been sold, before the panic, for $135,000, the value of real estate was greater then than at the time of the master’s sale. The proof did not sustain a greater value than $50,000 at the time of the sale, but if it be assumed- that this was somewhat inadequate, the fact that there was a depressed market for real estate would not be a sufficient circumstance, coupled with the supposed inadequacy in the bid, to warrant the chancellor in disapproving the master’s report of sale. The power to disapprove a sale for gross inadequacy of bid exists independent of an economic depression. The chancellor abused his discretion and erred in refusing to approve the sale at $50,000.</p> <p id=\"b292-3\" pgmap=\"292\">The judgment of the Appellate Court and the decree of the superior court are reversed and the cause is remanded to the superior court of Cook county, with directions to approve the master’s report of sale.</p> <p id=\"b292-4\" pgmap=\"292\">Reversed and remanded, with directions.</p> </opinion> <opinion type=\"concurrence\"> <author id=\"b292-5\" pgmap=\"292\">Stone and Shaw, JJ.,</author> <p id=\"ASY\" pgmap=\"292\">specially concurring:</p> <p id=\"b292-6\" pgmap=\"292\">We agree with the result reached but not in all that is said in the opinion.</p> </opinion> <opinion type=\"dissent\"> <author id=\"b293-2\" pgmap=\"293\">Mr. Chief Justice Herrick,</author> <p id=\"ADM\" pgmap=\"293\">dissenting:</p> <p id=\"b293-3\" pgmap=\"293\">I concur in the legal conclusion reached in the majority opinion that the chancellor had the power to fix an upset price for the sale of the property against which foreclosure was sought. He set the upset price on the re-sale order at $71,508.45. He found that the market value of the property was $80,000. The majority opinion shows that the hearing as to the value of the property was on affidavits. Those of appellant tended to establish a value of $40,000 to $50,000; those of appellee, from $77,400 to $80,000. The upset price established by the chancellor was clearly within the scope of the evidence. This court has consistently held on issues'involving the value of property, where the value was fixed by the verdict of a jury on conflicting evidence, that, in the absence of material error, this court would not disturb the finding of the jury where the amount determined was within the range of the evidence and not the result of passion and prejudice. (Department of Public Works v. Foreman Bank, 363 Ill. 13, 24.) In my opinion we should accord to the finding of the chancellor on the question of value the same credit we do to a verdict of a jury on that subject. The application of this rule to the instant cause would result in the affirmance of the decree. The judgment of the Appellate Court and the order of the superior court should each have been affirmed.</p> </opinion> <opinion type=\"dissent\"> <author id=\"b293-4\" pgmap=\"293\">Mr. Justice Orr,</author> <p id=\"AU6\" pgmap=\"293\">also dissenting:</p> <p id=\"b293-5\" pgmap=\"293\">I disagree with that portion of the opinion holding that a court of chancery, in a foreclosure case, has inherent power to fix an upset price to be bid at the sale. In my opinion, this court should adhere to the contrary rule laid down in Chicago Title and Trust Co. v. Robin, 361 Ill. 261.</p> </opinion> </casebody> ",
    #                 "data": '<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<casebody xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1" xmlns:xlink="http://www.w3.org/1999/xlink" firstpage="279" lastpage="293"><docketnumber id="b279-3" pgmap="279">(No. 23002.</docketnumber><parties id="b279-4" pgmap="279">Henry R. Levy, Appellant, vs. The Broadway-Carmen Building Corporation, Appellee.</parties><decisiondate id="b279-5" pgmap="279">Opinion filed April 16, 1937.</decisiondate><p id="b280-3" pgmap="280">Stone and Shaw, JJ., specially concurring.</p><p id="b280-4" pgmap="280">Herrick, C. J., and Orr, J., dissenting.</p><attorneys id="b280-6" pgmap="280">Isaac B. Lipson, (A. C. Lewis, of counsel,) for appellant.</attorneys><attorneys id="b280-7" pgmap="280">Kamfner, Halligan &amp; Marks, (Samuer M. Lanoff, of counsel,) for appellee.</attorneys> <opinion type="majority"> <author id="b280-8" pgmap="280">Mr. Justice Farthing</author> <p id="ADb" pgmap="280">delivered the opinion of the court:</p> <p id="b280-9" pgmap="280(154) 281(364) 282(102)">Henry R. Levy, the appellant, was the principal stockholder in the Studebaker Sales Company of Chicago. In January, 1926, David Gordon purchased the land involved in this foreclosure, from that company. He paid $35,000, in cash, and secured the balance of $100,000 by a mortgage. He reduced the debt to $70,000, and on April 13, 1931, when this became due, an agreement was made between Gordon and Levy by which $5000 more was paid and the property was deeded to the Broadway-Carmen Building Corporation, organized by Gordon. That company gave its note for $65,000, guaranteed by Gordon and his wife, and secured by a trust deed on the premises. In addition, Levy received a commission of " $1950. After $2500 had been paid on the principal debt, default was made by the mortgagor, and Levy obtained a judgment at law against David Gordon and Ida Gordon, his wife, for $66,691.87. He also brought this suit to foreclose the trust deed. The superior court of Cook county rendered a decree on May 26, 1933) and found that $70,246.91 was due Levy on March 15, 1933. It ordered the mortgaged premises sold at public auction and directed the master in chancery to carry out the decree. Accordingly the master, on June 21, 1933, struck off the property to appellant, Levy, for $50,000. The appellee filed objections to the report of sale. It claimed that the property was reasonably worth $80,000, but that economic conditions had resulted in the destruction of the market for real estate in Chicago. It prayed that the court establish the value of the premises and credit that value on the amount found due Levy; that a deficiency judgment be denied and that the judgment previously rendered against Gordon and wife, be satisfied in full. It stated that it had offered, and was then willing, to deed the property to the appellant in cancellation of the debt. Levy answered, denying that the premises were worth more than $50,000. He set up the fact that the property was being managed by a receiver and that the rental was $150 per month, plus $5 for each automobile sold by the lessee; that the 1929, 1930 and 1931 taxes, totalling $6000, were unpaid. He offered to assign his certificate of purchase to anyone for the amount of his bid. The mortgaged premises are located at a street intersection and are known as No. 5100 Broadway. The lot is 97 by 100 feet and is improved with a one-story automobile display building and service garage. Both parties introduced affidavits as to value. Those on behalf of appellee, set the value at $77,400 to $80,000, which was based on a rental value of $400 per month, and a possible rental of $500 if the building were divided into storerooms. The affidavits on behalf of appellant showed that the improvements cost $35,902 thirteen years before, and that their replacement value was $22,500. They showed the reasonable rental value to be $250 per month and fixed the value of the premises at from $40,000 to $50,000. At the close of the hearing on the objections, the chancellor ordered that the sale be approved, provided the appellant released and cancelled the outstanding judgment against the Gordons, and the mortgage indebtedness, but Levy refused to do this. A decree was entered on January 20, 1934, denying confirmation of the master’s report of sale. It ordered a re-sale of the property at an upset price of $71,508.45, the amount then due, together with interest and costs of suit. The Appellate Court for the First District affirmed this decree on appeal. We granted leave and the cause is here on appeal.</p> <p id="b282-3" pgmap="282">Appellant contends that the order of January 20, 1934, denying confirmation of the master’s report and directing a new sale at an upset price, was an amendment to the foreclosure decree dated May 26, 1933, and that the later decree was of no effect, because\'it was rendered at a succeeding term. This contention cannot be upheld. It was the duty of the court to supervise the sale and to approve or reject the report. If rejected, it was the duty of the court to order a re-sale and directions as to time, place and terms of sale were but incidents to such order. Mariner v. Ingraham, 230 Ill. 130; L. R A. 1915A, 699.</p> <p id="b282-4" pgmap="282(145) 283(382) 284(21)">As stated by appellant the remaining points for consideration are embodied in the question: May the chancellor, in a suit to foreclose a real estate mortgage, require the plaintiff to waive his right to a deficiency decree as a condition precedent to confirming the master’s report of sale, or, in the alternative, may the chancellor fix a value ■ and direct the master not to accept a bid lower than this reserved or upset price? Appellant says a court of equity is without power to disapprove a master’s report of sale in a foreclosure suit, except there be mistake, fraud or some violation of duty by the purchaser or the master. He says that no matter how grossly inadequate the bid may be, it does not constitute fraud, or warrant the chancellor in disapproving the sale. No argument is required to disclose or sustain the wisdom of the rule that public policy and the interest of debtors require stability in judicial sales and that these sales should not be disturbed without cause. However, it is to be observed that the rule requiring more than mere inadequacy of price, and the showing of a breach of duty by the purchaser or the officer, or a fraud upon the debtor, arose out of cases where the judicial sales had been consummated and not out of mere offers to buy from a court. For example in Skakel v. Cycle Trade Publishing Co. 237 Ill. 482, the complainant brought his action to set aside a sheriff’s sale and a deed already executed. The cases of Mixer v. Sibley, 53 Ill. 61, Davis v. Pickett, 72 id. 483, O’Callaghan v. O’Callaghan, 91 id. 228, and Smith v. Huntoon, 134 id. 24, all involved sales under executions at law. Dobbins v. Wilson, 107 Ill. 17, concerned a deed issued following a United States marshal’s sale. Quigley v. Breckenridge, 180 Ill. 627, involved a sale made pursuant to a decree for partition, and although we held that the sale was fair and the master’s report.of sale should have been approved, nevertheless we re-affirmed the doctrine that a court of chancery possesses a large discretion in passing upon masters’ reports of sale. In that case we pointed out the fact that such a sale is not completed until it is confirmed, and that until then, it confers no right in the land upon the purchaser. The sale in Bondurant v. Bondurant, 251 Ill. 324, was made by a trustee who had power to sell the land at public vendue and was not a judicial sale in the legal sense. In the case of Allen v. Shepard, 87 Ill. 314, we exercised our judicial power to determine whether or not the bid made at an administrator’s sale was adequate, and determined that it was. In Clegg v. Christensen, 346 Ill. 314, we again exercised the same power. Abbott v. Beebe, 226 Ill. 417, concerned a partition sale. The land brought more than two-thirds of the appraised value. We again declared that there was power in the chancellor to set aside a judicial sale for inadequacy of price but we held that the- facts showed the sale under consideration was fairly made. The record did not disclose any inadequacy in the price.</p> <p id="b284-3" pgmap="284">In sales by conservators, guardians and trustees, involving consideration of objections filed before reports of sale were approved, inadequacy of price has always been considered in determining whether the sale was fairly made and whether the report should be approved and confirmed. In most of the cases the objector tendered a larger bid and very often the bid was required to be secured, but the fact that there ,was such an increased bid was, at most, evidence that the sale price was inadequate. In Kloepping v. Stellmacher, 21 N. J. Eq. 328, a sheriff sold property worth $2000 for $52. The owner was ignorant, stupid and perverse, and would not believe his property would be sold for so trifling an amount, although he had been forewarned. Redemption was allowed upon payment of the purchase price and costs. The court said: “But when such gross inadequacy is combined with fraud or mistake, or any other ground of relief in equity, it will incline the court strongly to afford relief. The sale in this case is a great oppression on the complainants. They are ignorant, stupid, perverse and poor. They lose by it all their property, and are ill fitted to acquire more. They are such as this court should incline to protect, notwithstanding perverseness.”</p> <p id="b284-4" pgmap="284(111) 285(146)">In Graffam v. Burgess, 117 U. S. 180, 29 L. ed. 839, the Supreme Court of the United States, speaking through Mr. Justice Bradley, said: “It was formerly the rule in England, in chancery sales, that until confirmation of the master’s report, the bidding would be opened upon a mere offer to advance the price 10 per centum. (2 Daniell, Ch. Pr. 1st ed. 924; 2d ed. by Perkins, 1465, 1467; Sugden, V. &amp; P. 14th ed. 114.) But Lord Eldon expressed much dissatisfaction with this practice of opening biddings upon a mere offer of an advanced price, as tending to diminish confidence in such sales, to keep bidders from attending, and to diminish the amount realized. (White v. Wilson, 14 Ves. 151; Williams v. Attleborough, Tur. &amp; Rus. 76; White v. Damon, 7 Ves. 34.) Lord Eldon’s views were finally adopted in England in the Sale of Land by Auction act, 1857, (30 and 31 Victoria, chap. 48, sec. 7,) so that now the highest bidder at a sale by auction of land, under an order of the court, provided he has\'bid a sum equal to or higher than the reserved price (if any), will be declared and allowed the purchaser, unless the court or judge, on the ground of fraud or improper conduct in the management of the sale, upon the application of any person interested in the land, either opens the bidding or orders the property to be resold. 1 Sugden, V. &amp; P. 14th ed. by Perkins, 14 note (a).</p> <p id="b285-3" pgmap="285">“In this country Lord Eldon’s views were adopted at an early day by the courts; and the rule has become almost universal that a sale will not be set aside for inadequacy of price unless the inadequacy be so great as to shock the conscience, or unless there be additional circumstances against its fairness; being very much the rule that always prevailed in England as to setting aside sales after the master’s report had been confirmed. [Citing many cases.]</p> <p id="b285-4" pgmap="285">“From the cases here cited we may draw the general conclusion that if the inadequacy of price is so gross as to shock the conscience, or if in addition to gross inadequacy, the purchaser has been guilty of any unfairness, or has taken any undue advantage, or if the owner of the property, or party interested in it, has been for any other reason, misled or surprised, then the sale will be regarded as fraudulent and void, or the party injured will be permitted to redeem the property sold. Great inadequacy requires only slight circumstances of unfairness in the conduct of the party benefited by the sale to raise the presumption of fraud.”</p> <p id="b285-5" pgmap="285(22) 286(22)">In Pewabic Mining Co. v. Mason, 145 U. S. 349, 36 L. ed. 732, Mr. Justice Brewer said, at page 367: “Indeed even before confirmation the sale would not be set aside for mere inadequacy, unless so great as to shock the conscience.”</p> <p id="b286-3" pgmap="286">Stability must be given to judicial sales which have reached the point where title has vested in the purchaser, otherwise bidding would be discouraged. But where a bidder does not become vested with any interest in the land but has only made an offer to buy, subject to the approval of his offer by the court, and he bids with that condition, there can be no good reason why bidding would be discouraged by reason of the court’s power to approve or disapprove the sale for gross inadequacy of bid. Sales by masters are not sales in a legal sense, until they are confirmed. Until then, they are sales only in a popular sense. The accepted bidder acquires no independent right to\'have his purchase completed, but remains only a preferred proposer until confirmation of the sale by the court, as agreed to by its ministerial agent. Confirmation is final consent, and the court, being in fact the vendor, may consent or not, in its discretion. (Hart v. Burch, 130 Ill. 426; Jennings v. Dunphy, 174 id. 86; Pewabic Mining Co. v. Mason, supra; Smith v. Arnold, 5 Mason, 414.) In the case last •cited, Mr. Justice Story said, at page 420: “In sales directed by the court of chancery, the whole business is transacted by a public officer, under the guidance and superintendence of the court itself. Even after the sale is made, it is not final until a report is made to the court and it is approved and confirmed.”</p> <p id="b286-4" pgmap="286(86) 287(251)">Many of the decisions, relied upon and cited by appel- . lant, arose out of sales of lands under mortgages or trust deeds which contained a power of sale and were made at a time when there was no redemption, unless it was provided for in the mortgage or trust deed. Such sales were not subject to approval or disapproval by courts and the only remedy the mortgagor had against fraud or other misconduct was by a bill in equity to set aside the conveyanee, or for redemption. In 1843 the legislature passed an act regulating the foreclosure of mortgages on real property which created a redemption period in favor of mortgagors, but the act did not purport to govern trust deeds containing a power of sale. Thereafter the foreclosing of mortgages was committed to courts of chancery, under their general equity powers, except as to certain prescribed matters of procedure. From that time mortgage foreclosure sales were made by an officer who was required to report the sale to the court. Purchasers did not become vested with any interest in the land sold until the report of sale was approved. The court fixed the terms and conditions of foreclosure sales and this practice still continues. In 1879 the legislature provided that no real estate should be sold by virtue of any power of sale contained in any mortgage, trust deed, or other conveyance in the nature of a mortgage, but that thereafter such real estate should be sold in the same manner provided for foreclosure of mortgages containing no power of sale, and then only in pursuance of a judgment or decree of a court of competent jurisdiction. (State Bar Stat. 1935, chap. 95, par. 24; 95 S. H. A. 23.) The history of this legislation is conclusive proof that it was the legislative intent that foreclosure sales should be made only upon such terms and conditions as were approved by the courts. Garrett v. Moss, 20 Ill. 549.</p> <p id="b287-3" pgmap="287(103) 288(66)">Unfairness from any cause which operates to the prejudice of an interested party, will abundantly justify a chancery court in refusing to approve a sale. We said in Roberts v. Goodin, 288 Ill. 561: “The setting aside of the sale and ordering the property re-sold was a matter which rested largely within the discretion of the chancellor, whose duty it was to see that the lien be enforced with the least damage possible to the property rights of the mortgagor. Counsel cite numerous cases touching their contention that the chancellor erred in setting aside this sale. The cases cited, however, arose after the sale had once been confirmed, and not where, as here, the objection to the confirmation of the sale was filed immediately after the sale and before any confirmation had taken place. The chancellor has a broad discretion in the matter of approving or disapproving a master’s sale made subject to the court’s approval by the terms of the decree.”</p> <p id="b288-3" pgmap="288">The legislature’s purpose would be defeated if any other interpretation were given to the statutes on the subject of mortgage foreclosure. It is unusual for land to bring its full, fair market value at a forced sale. While courts can not guarantee that mortgaged property will bring its full value, they can prevent unwarranted sacrifice of a debtor’s property. Mortgage creditors resort to courts of equity for relief and those courts prescribe equitable terms upon which they may receive that relief, and it is within their power to prevent creditors from taking undue and unconscionable advantage of debtors, under the guise of collecting a debt. A slight inadequacy is not sufficient reason to disapprove a master’s sale, but where the amount bid is so grossly inadequate that it shocks the conscience of a court of equity, it is the chancellor’s duty to disapprove the report of sale. Connely v. Rue, 148 Ill. 207; Kiebel v. Reick, 216 id. 474; Wilson v. Ford, 190 id. 614; Ballentyne v. Smith, 205 U. S. 285, 51 L. ed. 803.</p> <p id="b288-4" pgmap="288(113) 289(137)">The case of Slack v. Cooper, 219 Ill. 138, illustrates the rule. In that case the master sold the land, upon which the mortgage had been foreclosed, to the solicitor for the mortgagor for $3000. He acted under the mistaken impression that the buyer was the solicitor for the mortgagee, who appeared shortly thereafter and bid $7000. The master then announced publicly that since no cash had been deposited by the original bidder, and because of the misapprehension stated and his haste in making the sale, it would be re-opened for higher and better bids. At page 144 of that decision we said: “If the chancellor finds upon the coming in of the report of a master, that the sale as made is not to the best interest of all concerned and is inequitable, or that any fraud or misconduct has been practiced upon the master or the court or any irregularities in the proceedings, it is his duty to set aside the sale as made and order another sale of the premises. The chancellor has a broad discretion in passing upon the acts of the master and approving or disapproving his acts in reference to sales and entering his own decrees, (Quigley v. Breckenridge, 180 Ill. 627,) and his decree will not be disturbed by this court unless it is shown that he has abused his discretion and entered such an order or decree as would not seem equitable between the parties interested.”</p> <p id="b289-3" pgmap="289">We have limited our discussion to the power of a court of chancery to approve or disapprove a master’s report of sale in a foreclosure suit and we hold that the court has broad discretionary powers over such sales. Where it appears that the bid offered the court for the premises is so grossly inadequate that its acceptance amounts to a fraud, the court has the power to reject the bid and order a re-sale.</p> <p id="b289-4" pgmap="289(159) 290(95)">There is little or no difference between the equitable jurisdiction\' and power in a chancery court to refuse approval to a report of sale on foreclosure, and the power to fix, in advance, a reserved or upset price, as a minimum at which the property may be sold. We have referred to the acts of 1843 and 1879 which require trust deeds and mortgages to be foreclosed in chancery courts and have pointed out that courts of equity, exercising their general equity powers in such cases, have the right to fix reasonable terms and conditions for the carrying out of the provisions of the foreclosure decree, and that such courts may order a new sale and set the old aside for the violation of some duty by the master, or for fraud or mistake. No reason appears why the chancellor cannot prevent a sale at a grossly inadequate price by fixing á reasonable sale price in advance. The same judicial power \'is involved in either action. What is necessary to be done in the end, to prevent fraud and injustice, may be forestalled by proper judicial action in the beginning. Such a course is not against the policy of the law in this State and it is not the equivalent of an appraisal statute. It is common practice in both the State and Federal courts to fix an upset price in mortgage foreclosure suits. This is in harmony with the accepted principles governing judicial power in mortgage foreclosures.</p> <p id="b290-3" pgmap="290">In First National Bank v. Bryn Mawr Beach Building Corp. 365 Ill. 409, we pointed out the fact that such property as was there under consideration seldom sells at anything like its reproduction cost, or even its fair cash market value, at a judicial sale. We recognized the fact that the equity powers of State courts are no more limited than those of Federal courts, and that equity jurisdiction over mortgage foreclosures is general rather than limited or statutory. In part we said: “It would seem that since equity courts have always exercised jurisdiction to decree the enforcement of mortgage liens and to supervise foreclosure sales, such jurisdiction need not expire merely because the questions or conditions surrounding the exercise of such time-honored functions are new or complicated. If it may reasonably be seen that the exercise of the jurisdiction of a court of equity beyond the sale of the property will result in better protection to parties before it, it would seem not only to be germane to matters of undisputed jurisdiction, but to make for the highest exercise of the court’s admitted functions.” We there held that a court of equity has jurisdiction, in connection with an application for approval of a foreclosure sale, to approve a re-organization plan submitted by a bondholders’ committee. The question is somewhat different from that presented in the case before us, but we there recognized the continuing vitality and growth of equity jurisprudence.</p> <p id="b291-2" pgmap="291">Cases wherein an upset price has been fixed are not confined to large properties for which, by reason of their great value, the market is limited or there is no market whatever. In McClintic-Marshall Co. v. Scandinavian-American Building Co. 296 Fed. 601, a building was constructed on two lots covered by the mortgage, and one lot belonging to the mortgagor that was not mortgaged. It was necessary, under the circumstances, to sell all the property, and to protect the mortgagor a reserved price was fixed. The fact of an upset price is referred to, although there was no objection to it being fixed, in Northern Pacific Railway Co. v. Boyd, 228 U. S. 482, 57 L. ed. 931, and Pewabic Mining Co. v. Mason, supra, and the power has been exercised in numerous other cases. 104 A. L. R. 375; 90 id. 1321; 88 id. 1481.</p> <p id="b291-3" pgmap="291">The appellant did not raise constitutional objections in the trial court and by appealing to the Appellate Court for the First District he would waive such questions. However, the fixing of an upset price does not violate section 10 of article 1 of the Federal constitution nor section 14 of article 2 of the Illinois constitution, which inhibit the impairment of the obligation of contracts. The reserved price dealt only with the remedy, and it was within the court’s power to establish it as one of the terms and conditions of the sale. The appellant was not deprived of his right to enforce the contract, and his remedy was neither denied, nor so embarrassed, as to seriously impair the value of his contract or the right to enforce it. Penniman’s Case, 103 U. S. 714, 26 L. ed. 502; Town of Cheney’s Grove v. Van Scoyoc, 357 Ill. 52.</p> <p id="b291-4" pgmap="291">It is contended that the present holding conflicts with what we said in Chicago Title and Trust Co. v. Robin, 361 Ill. 261. It was not necessary to that decision to pass upon the power to fix an upset price, and what we said on that subject is not adhered to.</p> <p id="b292-2" pgmap="292">Each case must be based upon its own facts, and from this record we are of the opinion that no such gross inadequacy existed in the bid of $50,000, as would warrant the chancellor in refusing approval of the master’s sale. Although the rents were pledged in the trust deed, they would amount to but little more than the taxes on the property of approximately $2000 per annum. Appellee’s affidavits base the estimate of value largely on the rental value of the premises. They were rented for $150 per month, plus $5 for each automobile sold by the lessee, and this amounted to a total of $200 a month. Even if the premises brought $400, or the $500 per month which appellee’s witnesses said could be had if the property was divided into storerooms, the cost of these changes is not given. This testimony did not warrant the chancellor in finding that these premises were worth $80,000. Although the property had been sold, before the panic, for $135,000, the value of real estate was greater then than at the time of the master’s sale. The proof did not sustain a greater value than $50,000 at the time of the sale, but if it be assumed- that this was somewhat inadequate, the fact that there was a depressed market for real estate would not be a sufficient circumstance, coupled with the supposed inadequacy in the bid, to warrant the chancellor in disapproving the master’s report of sale. The power to disapprove a sale for gross inadequacy of bid exists independent of an economic depression. The chancellor abused his discretion and erred in refusing to approve the sale at $50,000.</p> <p id="b292-3" pgmap="292">The judgment of the Appellate Court and the decree of the superior court are reversed and the cause is remanded to the superior court of Cook county, with directions to approve the master’s report of sale.</p> <p id="b292-4" pgmap="292">Reversed and remanded, with directions.</p> </opinion> <opinion type="concurrence"> <author id="b292-5" pgmap="292">Stone and Shaw, JJ.,</author> <p id="ASY" pgmap="292">specially concurring:</p> <p id="b292-6" pgmap="292">We agree with the result reached but not in all that is said in the opinion.</p> </opinion> <opinion type="dissent"> <author id="b293-2" pgmap="293">Mr. Chief Justice Herrick,</author> <p id="ADM" pgmap="293">dissenting:</p> <p id="b293-3" pgmap="293">I concur in the legal conclusion reached in the majority opinion that the chancellor had the power to fix an upset price for the sale of the property against which foreclosure was sought. He set the upset price on the re-sale order at $71,508.45. He found that the market value of the property was $80,000. The majority opinion shows that the hearing as to the value of the property was on affidavits. Those of appellant tended to establish a value of $40,000 to $50,000; those of appellee, from $77,400 to $80,000. The upset price established by the chancellor was clearly within the scope of the evidence. This court has consistently held on issues\'involving the value of property, where the value was fixed by the verdict of a jury on conflicting evidence, that, in the absence of material error, this court would not disturb the finding of the jury where the amount determined was within the range of the evidence and not the result of passion and prejudice. (Department of Public Works v. Foreman Bank, 363 Ill. 13, 24.) In my opinion we should accord to the finding of the chancellor on the question of value the same credit we do to a verdict of a jury on that subject. The application of this rule to the instant cause would result in the affirmance of the decree. The judgment of the Appellate Court and the order of the superior court should each have been affirmed.</p> </opinion> <opinion type="dissent"> <author id="b293-4" pgmap="293">Mr. Justice Orr,</author> <p id="AU6" pgmap="293">also dissenting:</p> <p id="b293-5" pgmap="293">I disagree with that portion of the opinion holding that a court of chancery, in a foreclosure case, has inherent power to fix an upset price to be bid at the sale. In my opinion, this court should adhere to the contrary rule laid down in Chicago Title and Trust Co. v. Robin, 361 Ill. 261.</p> </opinion> </casebody> ',
    #             }
    #         }
    #         self.read_json_func.return_value = harvard_data
    #         cluster = (
    #             OpinionClusterFactoryWithChildrenAndParents(
    #                 docket=DocketFactory(),
    #                 sub_opinions=RelatedFactoryList(
    #                     OpinionWithChildrenFactory,
    #                     factory_related_name="cluster",
    #                     size=3,
    #                 ),
    #             ),
    #         )
    #         test_idea = [
    #             ("020lead", "this is the first opinion"),
    #             ("030concurrence", "this is the the concurrence"),
    #             ("040dissent", "this is the dissent"),
    #         ]
    #         for op in Opinion.objects.filter(cluster_id=cluster[0].id):
    #             op_type, html_columbia = test_idea.pop()
    #             op.type = op_type
    #             op.html_columbia = html_columbia
    #             op.save()
    #
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1).count(),
    #             3,
    #             msg="Opinions not set up",
    #         )
    #         map_and_merge_opinions(cluster[0].id)
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1).count(),
    #             4,
    #             msg="Opinion not added",
    #         )
    #         self.assertEqual(cluster[0].id, 1, msg="NOT 2")
    #
    #         # this test should properly add an opinion lead to
    #
    #     def test_merge_opinion_children(self):
    #         """"""
    #         cluster = OpinionClusterFactoryMultipleOpinions(
    #             docket=DocketFactory(),
    #             sub_opinions__data=[
    #                 {
    #                     "type": "020lead",
    #                     "html_columbia": "<p>this is the lead opinion</p>",
    #                 },
    #                 {
    #                     "type": "030concurrence",
    #                     "html_columbia": "<p>this is the concurrence</p>",
    #                     "author_str": "kevin ramirez",
    #                 },
    #                 {
    #                     "type": "040dissent",
    #                     "html_columbia": "<p>this is the dissent</p>",
    #                 },
    #             ],
    #         )
    #         harvard_data = {
    #             "casebody": {
    #                 "data": "<?xml version='1.0' encoding='utf-8'?>\n<casebody> "
    #                 "<opinion>this is lead opinion</opinion> "
    #                 "<opinion>this is the the concurrence </opinion> "
    #                 "<opinion>this is the dissent</opinion> </casebody> ",
    #             }
    #         }
    #         self.read_json_func.return_value = harvard_data
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1).count(),
    #             3,
    #             msg="Opinions not set up",
    #         )
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1)[0].xml_harvard,
    #             "",
    #             msg="Shouldnt have opinion",
    #         )
    #         map_and_merge_opinions(cluster.id)
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1)[0].xml_harvard,
    #             "this is the first opinion",
    #             msg="Should have content",
    #         )
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1).count(),
    #             3,
    #             msg="Opinions not set up",
    #         )
    #
    #     def test_merge_opinions_opinions(self):
    #         # cluster = (
    #         #     OpinionClusterFactory(
    #         #         docket=DocketFactory(),
    #         #     ),
    #         # )
    #         # test_idea = [
    #         #     ("040dissent", "this is the dissent"),
    #         #     ("030concurrence", "this is the the concurrence"),
    #         #     ("020lead", "this is the first opinion"),
    #         # ]
    #         # for idea in test_idea:
    #         #     OpinionFactory.create(
    #         #         cluster=cluster[0],
    #         #         type=idea[0],
    #         #         html_columbia=idea[1]
    #         #     )
    #         cluster = OpinionClusterFactory(docket=DocketFactory())
    #         test_idea = [
    #             ("040dissent", "this is the dissent"),
    #             ("030concurrence", "this is the the concurrence"),
    #             ("020lead", "this is the first opinion"),
    #         ]
    #         for idea in test_idea:
    #             OpinionFactory.create(
    #                 cluster=cluster, type=idea[0], html_columbia=idea[1]
    #             )
    #
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=1).count(),
    #             3,
    #             msg="Opinions not set up",
    #         )
    #
    #         # cluster = (
    #         #     OpinionClusterFactoryWithChildrenAndParents(
    #         #         docket=DocketFactory(),
    #         #         sub_opinions=RelatedFactoryList(
    #         #             OpinionWithChildrenFactory,
    #         #             factory_related_name="cluster",
    #         #             size=3
    #         #         )
    #         #     ),
    #         # )
    #         # self.assertEqual(cluster[0].id, 1, msg="hmmm")
    #         # self.assertEqual(Opinion.objects.filter(cluster__id=cluster[0].id).count(), 3, msg="Opinion are tough")
    #
    #         # harvard_data = {
    #         #     "casebody": {
    #         #         "data": "<?xml version='1.0' encoding='utf-8'?>\n<casebody> "
    #         #                 "<opinion>this is the first opinion </opinion> "
    #         #                 "<opinion>this is the the concurrence </opinion> "
    #         #                 "<opinion>this is the dissent</opinion> </casebody> ",
    #         #     }
    #         # }
    #         # self.read_json_func.return_value = harvard_data
    #         # test_idea = [
    #         #     ("040dissent", "this is the dissent"),
    #         #     ("030concurrence", "this is the the concurrence"),
    #         #     ("020lead", "this is the first opinion"),
    #         # ]
    #         # for op in Opinion.objects.filter(cluster_id=cluster[0].id):
    #         #     op_type, html_columbia = test_idea.pop()
    #         #     op.type = op_type
    #         #     op.html_columbia = html_columbia
    #         #     op.save()
    #         #
    #         # self.assertEqual(Opinion.objects.filter(cluster__id=1).count(), 3, msg="Opinions not set up")
    #         # map_and_merge_opinions(cluster[0].id)
    #         # self.assertEqual(Opinion.objects.filter(cluster__id=1).count(), 3, msg="Opinion added weird")
    #         #
    #         # for op in Opinion.objects.filter(cluster__id=1):
    #         #     self.assertEqual(op.html_columbia, op.xml_harvard, msg="NOT MATCHED")
    #
    #     def test_merger(self):
    #         # import requests
    #         # r = requests.get('https://ia903106.us.archive.org/18/items/law.free.cap.ga-app.71/757.1525757.json').json()
    #         r = {
    #             "name": "CANNON v. THE STATE",
    #             "name_abbreviation": "Cannon v. State",
    #             "decision_date": "1944-11-18",
    #             "docket_number": "30614",
    #             "casebody": {
    #                 "status": "ok",
    #                 "data": '<casebody firstpage="757" lastpage="758" xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1">\n  <docketnumber id="b795-7">30614.</docketnumber>\n  <parties id="AAY">CANNON <em>v. </em>THE STATE.</parties>\n  <decisiondate id="b795-9">Decided November 18, 1944.</decisiondate>\n  <attorneys id="b796-4"><page-number citation-index="1" label="758">*758</page-number><em>B. B. Giles, </em>for plaintiff in error.</attorneys>\n  <attorneys id="b796-5"><em>Lindley W. Gamp, solicitor, John A. Boyhin, solicitor-general,. Durwood T. Bye, </em>contra.</attorneys>\n  <opinion type="majority">\n    <author id="b796-6">Broyles, C. J.</author>\n    <p id="Auq">(After stating the foregoing facts.) After the-disposal of counts 2 and 3, the only charge before the court and jury was that the defendant had sold distilled spirits and alcohol as a retail dealer, without first obtaining a license from the State Revenue Commissioner. The evidence adduced to show the guilt, of the accused on count 1 was wholly circumstantial, and was insufficient to exclude every reasonable hypothesis except that of his-guilt, and it failed to show beyond a reasonable doubt that he had sold distilled spirits or alcohol. The cases of <em>Thomas </em>v. <em>State, </em>65 <em>Ga. App. </em>749 (16 S. E. 2d, 447), and <em>Martin </em>v. <em>State, </em>68 <em>Ga. App. </em>169 (22 S. E. 2d, 193), cited in behalf of the defendant in error, are distinguished by their facts from this case. The verdict was-contrary to law and the evidence; and the overruling of the certiorari was error. <em>Judgment reversed.</em></p>\n    <judges id="Ae85">\n      <em>MacIntyre, J., concurs.</em>\n    </judges>\n  </opinion>\n  <opinion type="concurrence">\n    <author id="b796-7">Gardner, J.,</author>\n    <p id="AK2">concurring specially: Under the record the judgment should be reversed for another reason. Since the jury, based on the same evidence, found the defendant not guilty on count 2 for possessing liquors, and a verdict finding him guilty on count 1 for selling intoxicating liquors, the verdicts are repugnant and void as being inconsistent verdicts by the same jury based on the same \'evidence. <em>Britt </em>v. <em>State, </em>36 <em>Ga. App. </em>668 (137 S. E. 791), and cit.; <em>Kuck </em>v. <em>State, </em>149 <em>Ga. </em>191 (99 S. E. 622). I concur in the reversal for this additional reason.</p>\n  </opinion>\n</casebody>\n',
    #             },
    #         }
    #         self.read_json_func.return_value = r
    #
    #         lead = """<p>The overruling of the certiorari was error.</p>
    # <p><center>                       DECIDED NOVEMBER 18, 1944.</center>
    # John Cannon was tried in the criminal court of Fulton County on an accusation containing three counts. Count I charged that in said county on July 24, 1943, he "did engage in and sell, as a retail dealer, distilled spirits and alcohol, without first obtaining a license from the State Revenue Commissioner of the State of Georgia." Count 2 charged that on July 24, 1943, he possessed forty-eight half pints and three pints of whisky in Fulton County, and had not been licensed by the State Revenue Commissioner to sell whisky as a retail or wholesale dealer. Count 3 charged that on September 24, 1943, in said county, he sold malt beverages as a retail dealer, without first securing a license from the State Revenue Commissioner. On the trial, after the close of the State's evidence, counsel for the accused made a motion that count 2 be stricken, and that a verdict for the defendant be directed on counts 1 and 3. The court sustained the motion as to counts 2 and 3, but overruled it as to count 1. The jury returned a verdict of guilty on count 1, and of not guilty on counts 2 and 3. Subsequently the defendant's certiorari was overruled by a judge of the superior court and that judgment is assigned as error. <span class="star-pagination">*Page 758</span>
    # After the disposal of counts 2 and 3, the only charge before the court and jury was that the defendant had sold distilled spirits and alcohol as a retail dealer, without first obtaining a license from the State Revenue Commissioner. The evidence adduced to show the guilt of the accused on count 1 was wholly circumstantial, and was insufficient to exclude every reasonable hypothesis except that of his guilt, and it failed to show beyond a reasonable doubt that he had sold distilled spirits or alcohol. The cases of <em>Thomas</em> v. <em>State,</em> <cross_reference><span class="citation no-link">65 Ga. App. 749</span></cross_reference> (<cross_reference><span class="citation" data-id="3407553"><a href="/opinion/3412403/thomas-v-state/">16 S.E.2d 447</a></span></cross_reference>), and <em>Martin</em> v. <em>State,</em> <cross_reference><span class="citation no-link">68 Ga. App. 169</span></cross_reference> (<cross_reference><span class="citation" data-id="3405716"><a href="/opinion/3410794/martin-v-state/">22 S.E.2d 193</a></span></cross_reference>), cited in behalf of the defendant in error, are distinguished by their facts from this case. The verdict was contrary to law and the evidence; and the overruling of the certiorari was error.</p>
    # <p><em>Judgment reversed. MacIntyre, J., concurs.</em></p>"""
    #         concurrence = """<p>Under the record the judgment should be reversed for another reason. Since the jury, based on the same evidence, found the defendant not guilty on count 2 for possessing liquors, and a verdict finding him guilty on count 1 for selling intoxicating liquors, the verdicts are repugnant and void as being inconsistent verdicts by the same jury based on the same evidence. <em>Britt</em> v. <em>State,</em> <cross_reference><span class="citation no-link">36 Ga. App. 668</span></cross_reference>
    # (<cross_reference><span class="citation no-link">137 S.E. 791</span></cross_reference>), and cit.; <em>Kuck</em> v. <em>State,</em> <cross_reference><span class="citation" data-id="5582722"><a href="/opinion/5732248/kuck-v-state/">149 Ga. 191</a></span></cross_reference>
    # (<cross_reference><span class="citation no-link">99 S.E. 622</span></cross_reference>). I concur in the reversal for this additional reason.</p>"""
    #         cluster = OpinionClusterFactoryMultipleOpinions(
    #             docket=DocketFactory(),
    #             sub_opinions__data=[
    #                 {"type": "020lead", "html_with_citations": lead},
    #                 {"type": "030concurrence", "html_with_citations": concurrence},
    #             ],
    #         )
    #         self.assertEqual(Opinion.objects.all().count(), 2)
    #         merge_opinion_clusters(cluster_id=cluster.id)
    #         self.assertEqual(Opinion.objects.all().count(), 2)
    #
    #     def test_merge_case_names(self):
    #         self.read_json_func.return_value = {
    #             "name": "KELLEY’S ESTATE",
    #             "name_abbreviation": "Kelley's Estate",
    #         }
    #         cluster = (
    #             OpinionClusterFactoryWithChildrenAndParents(
    #                 docket=DocketFactory(
    #                     case_name_short="",
    #                     case_name="",
    #                     case_name_full="",
    #                 ),
    #                 case_name_short="",
    #                 case_name="Kelley's Estate",
    #                 case_name_full="KELLEY’S ESTATE",
    #                 date_filed=date.today(),
    #                 sub_opinions=RelatedFactory(
    #                     OpinionWithChildrenFactory,
    #                     factory_related_name="cluster",
    #                 ),
    #             ),
    #         )
    #         start_merger(cluster_id=cluster[0].id)
    #
    #         self.assertEqual(
    #             cluster[0].case_name,
    #             cluster[0].sub_opinions.all().first().author_str,
    #         )
    #
    #     # def test_merge_judges(self):
    #     #     """
    #     #     discrepenacy in the first name an H or no H
    #     #     this example comes from
    #     #     Cluster, Harvard ID
    #     #     (2027381, 6554605)
    #     #
    #     #     """
    #     #     harvard_data = {
    #     #         "casebody": {
    #     #             "data": "<casebody> <author>JOHN J. CHINEN, Bankruptcy Judge.</author><opinion> *xyz </opinion>\n</casebody>\n"
    #     #         }
    #     #     }
    #     #     cluster = OpinionClusterFactoryWithChildrenAndParents(
    #     #         docket=DocketFactory(),
    #     #         judges="Jon J. Chinen",
    #     #     )
    #     #     judge_matches = judges_in_harvard(cluster, harvard_data)
    #     #     self.assertTrue(judge_matches)
    #     #
    #     #     # ('Lamar W. Davis, Jr.', 'Davis')
    #     #     harvard_data = {
    #     #         "casebody": {
    #     #             "data": "<casebody> <author>LAMAR W. DAVIS, JR., Bankruptcy Judge.</author><opinion> *xyz </opinion>\n</casebody>\n"
    #     #         }
    #     #     }
    #     #     cluster = OpinionClusterFactoryWithChildrenAndParents(
    #     #         docket=DocketFactory(),
    #     #         judges="Lamar W. Davis, Jr.",
    #     #     )
    #     #     judge_matches = judges_in_harvard(cluster, harvard_data)
    #     #     self.assertTrue(judge_matches)
    #     #
    #     #     # Cluster: 2597372 Harvard_id: 299727 #law.free.cap.f-supp.89/545.299727.json
    #     #     harvard_data = {
    #     #         "casebody": {
    #     #             "data": '<casebody>\n  <parties id="b597-14">PENNER INSTALLATION CORPORATION v. UNITED STATES.</parties>\n  <docketnumber id="b597-15">No. 47266.</docketnumber>\n  <court id="b597-16">United States Court of Claims.</court>\n  <decisiondate id="b597-17">April 3, 1950.</decisiondate>\n  <attorneys id="b598-21"><page-number citation-index="1" label="546">*546</page-number>Albert Foreman, New York City, for the plaintiff. M. Carl Levine, Morgulas &amp; Foreman, New York City, were on the brief.</attorneys>\n  <attorneys id="b598-22">John R. Franklin, Washington, D. C., with whom was Assistant Attorney General H. G. Morison, for the defendant.</attorneys>\n  <p id="b598-23">Before JONES, Chief Judge, and WHITAKER, HOWELL, MADDEN and LITTLETON, Judges.</p>\n  <opinion type="majority">\n    <author id="b598-24">WHITAKER, Judge.</author>\n   </opinion>\n</casebody>\n'
    #     #         }
    #     #     }
    #     #     cluster = OpinionClusterFactoryWithChildrenAndParents(
    #     #         docket=DocketFactory(),
    #     #         judges="Jones, Chief Judge, and Whitaker, Howell, Madden and Littleton, Judges",
    #     #     )
    #     #     judge_matches = judges_in_harvard(cluster, harvard_data)
    #     #     self.assertTrue(judge_matches)
    #
    #     def test_docket_number_merges(self):
    #         """"""
    #         # /storage/harvard_corpus/law.free.cap.mj.74/793.4355654.json
    #         # ----
    #         # Cluster: 2829548 Harvard_id: 4355654
    #         # id               (2829548, 4355654)
    #         # docket_number            ('201400102', 'NMCCA 201400102 GENERAL COURT-MARTIAL')
    #         harvard_data = {
    #             "docket_number": "NMCCA 201400102 GENERAL COURT-MARTIAL",
    #         }
    #         cluster = OpinionClusterFactoryWithChildrenAndParents(
    #             docket=DocketFactory(
    #                 docket_number="201400102", docket_number_core=""
    #             ),
    #         )
    #
    #         # /storage/harvard_corpus/law.free.cap.f-supp-3d.352/1312.12528902.json
    #         # ----
    #         # Cluster: 4568330 Harvard_id: 12528902
    #         # id               (4568330, 12528902)
    #         # judges           ('Choe-Groves', 'Choe, Groves')
    #         # docket_number            ('17-00031', 'Slip Op. 18-165; Court No. 17-00031')
    #         harvard_data = {
    #             "docket_number": "Slip Op. 18-165; Court No. 17-00031",
    #         }
    #         cluster = OpinionClusterFactoryWithChildrenAndParents(
    #             docket=DocketFactory(
    #                 docket_number="17-00031", docket_number_core=""
    #             ),
    #         )
    #         # How do we handle slip opinions...
    #         # there are so many variations
    #
    #         # /storage/harvard_corpus/law.free.cap.vet-app.28/222.12274823.json
    #         # ----
    #         # Cluster: 4248491 Harvard_id: 12274823
    #         # id               (4248491, 12274823)
    #         # case_name                ('Garzav. McDonald', 'Garza v. McDonald')
    #         # docket_number            ('14-2711', 'No. 14-2711')
    #
    #         harvard_data = {
    #             "docket_number": "No. 14-2711",
    #         }
    #         cluster = OpinionClusterFactoryWithChildrenAndParents(
    #             docket=DocketFactory(
    #                 docket_number="14-2711", docket_number_core=""
    #             ),
    #         )
    #
    #     def test_case_name_merger(self):
    #         """"""
    #
    #         harvard_data = {
    #             "name": "Travelodge International, Inc. v. Continental Properties, Inc. (In re Continental Properties, Inc.)",
    #             "name_abbreviation": "",
    #             "casebody": {
    #                 "data": "<casebody> <author>JOHN J. CHINEN, Bankruptcy Judge.</author><opinion> *xyz </opinion>\n</casebody>\n"
    #             },
    #         }
    #         cluster = OpinionClusterFactoryWithChildrenAndParents(
    #             docket=DocketFactory(
    #                 case_name_short="",
    #                 case_name="",
    #                 case_name_full="",
    #             ),
    #             case_name_short="",
    #             case_name="In Re Continental Properties, Inc",
    #             case_name_full="",
    #         )
    #
    #         # With dockets, im ready to say that if adocket when normalized is a subset of the toher we overwrite the docket
    #
    #     def test_wrong_opinion_total(self):
    #         """"""
    #         # https://www.courtlistener.com/opinion/3246772/tyler-v-state/
    #         # http://archive.org/download/law.free.cap.ala-app.19/380.8825727.json
    #
    #         harvard_data = {
    #             "casebody": {
    #                 "data": '<casebody firstpage="380" lastpage="383" xmlns="http://nrs.harvard.edu/urn-3:HLS.Libr.US_Case_Law.Schema.Case_Body:v1">\n  <citation id="b396-21">(97 South. 573)</citation>\n  <citation id="A05o">(6 Div. 152.)</citation>\n  <parties id="b396-22">TYLER v. STATE.</parties>\n  <court id="b396-23">(Court of Appeals of Alabama.</court>\n  <decisiondate id="AVW">April 3, 1923.</decisiondate>\n  <otherdate id="AKHV">Rehearing Denied April 17, 1923.</otherdate>\n  <otherdate id="Ahci">Affirmed\' on Mandate July 10, 1923.</otherdate>\n  <otherdate id="Aan">Rehearing Denied Oct. 16, 1923.)</otherdate>\n  <attorneys id="b398-8"><page-number citation-index="1" label="382">*382</page-number>Pinkney Scott, of Bessemer, for appellant.</attorneys>\n  <attorneys id="b398-10">Harwell G. Davis, Atty. Gen., and Lamar Eield, Asst.\' Atty. Gen., and Ben G. Perry, of Bessemer, for the State.</attorneys>\n  <opinion type="majority">\n    <author id="b398-13">BRICKEN, P. J.</author>\n    <p id="AvZ1">This is the third appeal in this case; the first being from an order of the judge of the circuit court denying defendant bail, and resulting in an affirmance here. Ex parte Tyler, 17 Ala. App. 698, 89 South. 926. The second appeal was from a judgment of conviction for murder in the first degree resulting in a reversal by the Supreme Court. Tyler v. State, 207 Ala. 129, 92 South. 478.</p>\n    <p id="b398-14">The evidence offered by the state tended to show that the defendant, on December 12, 1920, while under the influence of liquor, went to the home of J. M. Tyler, defendant’s father, where the deceased was a guest visiting the widowed sister of the defendant, Mrs. Silvia; that defendant had protested against deceased’s attention to Mrs. Silvia; that when defendant arrived at the home of his father the deceased was playing with two, of Mrs. Silvia’s children in the kitchen, and that Mrs. Silvia and the baby were in the adjoining room; that defendant, without the slightest provocation or semblance of justification, shot the deceased, inflicting upon his person wounds that caused his death.</p>\n    <p id="b398-15">The defendant offered some evidence tending to show that he was on his way to his brother’s, carrying his brother some medicine; that he stopped by his father’s home, and entered the home by the kitchen door; that deceased seized and attacked\' him; and, in a scuffle for defendant’s pistol, the weapon was discharged, inflicting the wounds that caused the death of the deceased.</p>\n    <p id="b398-16">The defendant’s motion to quash the venire and his objecting to being put to trial because two of the veniremen drawn for the defendant’s trial had served as jurors on the former trial of the defendant was without merit, and was\'properly overruled. Stover v. State, 204 Ala. 311, 85 South. 393; Morris v. State, 18 Ala. App. 135, 90 South. 57.</p>\n    <p id="b398-17">The veniremen who had served on the jury on the previous trial were subject to challenge for cause and by exercising the right of challenge for cause, if they were objectionable to defendant, these veniremen would have been stricken from the list, without curtailing the defendant’s strikes or peremptory challenges. Wickard v. State,” 109 Ala. 45, 19 South. 491; Stover v. State, supra.</p>\n    <p id="b398-18">The question addressed to Mary Alexander, “Who -\\yere your physicians, who treated him?” and that addressed to Dr. Wilkinson, “How long have you known him (deceased) ?” were preliminary in character, and the defendant’s objection was properly overruled.</p>\n    <p id="b398-19"> There was evidence tending to show that the motive prompting the homicide was <page-number citation-index="1" label="383">*383</page-number>to put an end to the attention the deceased was showing Mrs. Silvia, and her testimony that her husband was dead, that she was living at her father’s, that she was the mother of the children present in the house at the time of the homicide, and the ages of the children, was not without relevancy as shedding light on the motive of the defendant and the conduct of the deceased at the( time of the homicide. While evidence as to motive is not essential, it is always competent. Jones v. State, 13 Ala. App. 10, 68 South. 690; Brunson v. State, 124 Ala. 40, 27 South. 410.</p>\n    <p id="b399-4"> It is not essential that a dying declaration, if made under a sense of impending death, should be wholly voluntary.</p>\n    <blockquote id="b399-5">They “are admitted upon the theory that the consciousness of approaching death dispels from the mind all motive for making a false statement, in view of the fact that the party recognizes the fact that he shall soon appear in the.presence of his Maker.” Parker v. State, 165 Ala. 1, 51 South. 260.</blockquote>\n    <p id="b399-6">The predicate was sufficient to authorize the admission of the dying declaration. Tyler v. State; 207 Ala. 129, 92 South. 478.</p>\n    <p id="b399-7">The testimony /Of the witness Mrs. George Silvia, given on the preliminary trial, was only admissible to impeach her testimony on the present trial, after proper predicate had beeji laid for such purpose, and the court properly admitted such as •tended to contradict her and corresponding to the several predicates laid on her cross-examination, and properly excluded the other portion of her testimony.</p>\n    <p id="b399-8">The witness, Mrs. E. S. Tyler, testified: “I did not say in that statement that Lon was drunk, but he must have been drunk or something, I reckon, but I don’t know how that was,” and so much of the written signed statement made by this witness, to wit, “Lon was drunk” was admissible to contradict her -testimony; hence the defendant’s general objection to all of the statement, was not well taken. Longmire v. State, 130 Ala. 67, 30 South. 413; Wright v. State, 136 Ala. 139, 145, 34 South. 233.</p>\n    <p id="b399-9">The solicitor, in his closing argument to the jury\', made the following statements to the jury: “We have got too much killing around here.” “Don’t you know we have.” “Do you know why?” The defendant objected to each of these statements and moved to exclude them because they were improper. The court overruled the defendant’s objection and motion and to these rulings the defendant reserved, exception.</p>\n    <p id="b399-10">In each of these rulings the court committed reversible error. The statement of the solicitor, “We have got too much killing around here,” was the statement of a fact, of which there was no evidence, and if evidence had been offered of this fact it would not have been admissible. Alabama Fuel <em>&amp; </em>Iron Co. v. Williams, 207 Ala. 99, 91 South. 879; McAdory v. State, 62 Ala. 154; Cross v. State, 68 Ala. 476; Flowers v. State, 15 Ala. App. 220, 73 South. 126; Strother v. State, 15 Ala. App. 106, 72 South. 566; B. R. L. &amp; P. Co. v. Drennen, 175 Ala. 349, 57 South. 876, Ann. Cas. 1914C, 1037; B’ham Ry. L. &amp; P. Co. v. Gonzalez, 183 Ala. 273, 61 South. 80, Ann. Cas. 1916A, 543.</p>\n    <p id="b399-12">In some of the authorities cited, the Supreme Court said:</p>\n    <blockquote id="b399-13">“However reluctant an appellate court may be to interfere with the discretion of a primary court in regulating the trial of causes, if it should appear that it had refused, to the prejudice of a party, to compel counsel to confine their arguments and comments to the jury, to the law and evidence of the case under consideration — if it had permitted them to.refer to and comment upon facts not in evidence, or which would not be admissible as evidence, it would be a fatal error.” 62 Ala. 163.</blockquote>\n    <blockquote id="b399-14">. “Now, there was not only no evidence before the jury of that other homicide, or its details, but such evidence, if offered, would have been illegal and irrelevant. This was not argument, and could furnish no .safe or permissible aid to the jury in considering and weighing the testimony before them. The jury\', in their deliberations, should consider no facts, save those given in evidence.” 68 Ala. 476.</blockquote>\n    <p id="b399-15">The statements here brought in question were not only argument, but their scope and. effect, however innocently made, was an appeal to the mob spirit to convict the defendant, regardless of the evidence because other killings had occurred in that county. The tendency and effect of their argument was to incense the minds of the jury and draw them away from the facts in the case. The defendant was entitled to have his case tried on the evidence, without regard to other killings. The argument of defendant’s counsel was clearly within the issues and the improper argument of the solicitor cannot be justified on the theory that it was made in answer to the argument of defendant’s attorney. . -</p>\n    <p id="b399-16">Charge 1, refused to the defendant, assumes that Lon Tyler was a guest at his father’s house, and was invasive of the province of the jury. Charge 2 is argumentative, elliptical, and otherwise faulty. Charge 4 is involved and relieved the defendant fr-om the duty of retreating. Charge 5 pretermits imminent danger. Charge 7 was properly refused; the burden is not on the state to “disprove” that defendant was not free from fault. Charge 8 is not the law. Charge 9 is bad. Deliberation and premeditation is not essential to murder in the second degree.</p>\n    <p id="b399-17">For the error pointed out, the judgment is reversed.</p>\n    <p id="b399-18">Reversed and remanded.</p>\n    <author id="b399-19">PER CURIAM.</author>\n    <p id="ARX">Affirmed on authority of Ex parte State, ex rel. Attorney General, In re Lon Tyler v. State, 210 Ala. 96, 97 South. 573.</p>\n  </opinion>\n</casebody>\n',
    #                 "status": "ok",
    #             }
    #         }
    #         cluster = OpinionClusterWithParentsFactory.create()
    #
    #         # We have a p
    #         OpinionFactory.create(
    #             cluster=cluster,
    #             type="010combined",
    #         )
    #         OpinionFactory.create(
    #             cluster=cluster,
    #             type="050addendum",
    #         )
    #         self.assertEqual(cluster.id, 1, msg="wrong id")
    #         self.assertEqual(
    #             Opinion.objects.all().count(),
    #             2,
    #             msg=f"{Opinion.objects.all().count()}",
    #         )
    #         self.assertEqual(
    #             Opinion.objects.filter(cluster__id=cluster).count(),
    #             2,
    #             msg="Wrong total",
    #         )
