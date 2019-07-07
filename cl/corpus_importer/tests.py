# coding=utf-8
import json
import os
import unittest
from datetime import date

import pytest
from django.conf import settings
from django.test import TestCase

from cl.corpus_importer.court_regexes import match_court_string
from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.corpus_importer.import_columbia.parse_opinions import \
    get_state_court_object
from cl.corpus_importer.tasks import generate_ia_json
from cl.corpus_importer.utils import get_start_of_quarter
from cl.lib.pacer import process_docket_data
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.models import UPLOAD_TYPE
from cl.recap.tasks import find_docket_object
from cl.search.models import Docket, RECAPDocument


class JudgeExtractionTest(unittest.TestCase):
    def test_get_judge_from_string_columbia(self):
        """Can we cleanly get a judge value from a string?"""
        tests = ((
            'CLAYTON <italic>Ch. Jus. of the Superior Court,</italic> '
            'delivered the following opinion of this Court: ',
            ['clayton'],
        ), (
            'OVERTON, J. &#8212; ',
            ['overton'],
        ), (
            'BURWELL, J.:',
            ['burwell'],
        ))
        for q, a in tests:
            self.assertEqual(find_judge_names(q), a)


class CourtMatchingTest(unittest.TestCase):
    """Tests related to converting court strings into court objects."""

    def test_get_court_object_from_string(self):
        """Can we get a court object from a string and filename combo?

        When importing the Columbia corpus, we use a combination of regexes and
        the file path to determine a match.
        """
        pairs = (
            {
                'args': (
                    "California Superior Court  "
                    "Appellate Division, Kern County.",
                    'california/supreme_court_opinions/documents/0dc538c63bd07a28.xml',  # noqa
                ),
                'answer': 'calappdeptsuperct'
            },
            {
                'args': (
                    "California Superior Court  "
                    "Appellate Department, Sacramento.",
                    'california/supreme_court_opinions/documents/0dc538c63bd07a28.xml',  # noqa
                ),
                'answer': 'calappdeptsuperct'
            },
            {
                'args': (
                    "Appellate Session of the Superior Court",
                    'connecticut/appellate_court_opinions/documents/0412a06c60a7c2a2.xml',  # noqa
                ),
                'answer': 'connsuperct'
            },
            {
                'args': (
                    "Court of Errors and Appeals.",
                    'new_jersey/supreme_court_opinions/documents/0032e55e607f4525.xml',  # noqa
                ),
                'answer': 'nj'
            },
            {
                'args': (
                    "Court of Chancery",
                    'new_jersey/supreme_court_opinions/documents/0032e55e607f4525.xml',  # noqa
                ),
                'answer': 'njch'
            },
            {
                'args': (
                    "Workers' Compensation Commission",
                    'connecticut/workers_compensation_commission/documents/0902142af68ef9df.xml',  # noqa
                ),
                'answer': 'connworkcompcom',
            },
            {
                'args': (
                    'Appellate Session of the Superior Court',
                    'connecticut/appellate_court_opinions/documents/00ea30ce0e26a5fd.xml'  # noqa
                ),
                'answer': 'connsuperct',
            },
            {
                'args': (
                    'Superior Court  New Haven County',
                    'connecticut/superior_court_opinions/documents/0218655b78d2135b.xml'  # noqa
                ),
                'answer': 'connsuperct',
            },
            {
                'args': (
                    'Superior Court, Hartford County',
                    'connecticut/superior_court_opinions/documents/0218655b78d2135b.xml'  # noqa
                ),
                'answer': 'connsuperct',
            },
            {
                'args': (
                    "Compensation Review Board  "
                    "WORKERS' COMPENSATION COMMISSION",
                    'connecticut/workers_compensation_commission/documents/00397336451f6659.xml',  # noqa
                ),
                'answer': 'connworkcompcom',
            },
            {
                'args': (
                    'Appellate Division Of The Circuit Court',
                    'connecticut/superior_court_opinions/documents/03dd9ec415bf5bf4.xml',  # noqa
                ),
                'answer': 'connsuperct',
            },
            {
                'args': (
                    'Superior Court for Law and Equity',
                    'tennessee/court_opinions/documents/01236c757d1128fd.xml',
                ),
                'answer': 'tennsuperct',
            },
            {
                'args': (
                    'Courts of General Sessions and Oyer and Terminer '
                    'of Delaware',
                    'delaware/court_opinions/documents/108da18f9278da90.xml',
                ),
                'answer': 'delsuperct',
            },
            {
                'args': (
                    'Circuit Court of the United States of Delaware',
                    'delaware/court_opinions/documents/108da18f9278da90.xml',
                ),
                'answer': 'circtdel',
            },
            {
                'args': (
                    'Circuit Court of Delaware',
                    'delaware/court_opinions/documents/108da18f9278da90.xml',
                ),
                'answer': 'circtdel',
            },
            {
                'args': (
                    'Court of Quarter Sessions '
                    'Court of Delaware,  Kent County.',
                    'delaware/court_opinions/documents/f01f1724cc350bb9.xml',
                ),
                'answer': 'delsuperct',
            },
            {
                'args': (
                    "District Court of Appeal.",
                    'florida/court_opinions/documents/25ce1e2a128df7ff.xml',
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'District Court of Appeal, Lakeland, Florida.',
                    'florida/court_opinions/documents/25ce1e2a128df7ff.xml',
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'District Court of Appeal Florida.',
                    'florida/court_opinions/documents/25ce1e2a128df7ff.xml',
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'District Court of Appeal, Florida.',
                    'florida/court_opinions/documents/25ce1e2a128df7ff.xml',
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'District Court of Appeal of Florida, Second District.',
                    'florida/court_opinions/documents/25ce1e2a128df7ff.xml',
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'District Court of Appeal of Florida, Second District.',
                    '/data/dumps/florida/court_opinions/documents/25ce1e2a128df7ff.xml',  # noqa
                ),
                'answer': 'fladistctapp',
            },
            {
                'args': (
                    'U.S. Circuit Court',
                    'north_carolina/court_opinions/documents/fa5b96d590ae8d48.xml',  # noqa
                ),
                'answer': 'circtnc',
            },
            {
                'args': (
                    "United States Circuit Court,  Delaware District.",
                    'delaware/court_opinions/documents/6abba852db7c12a1.xml',
                ),
                'answer': 'circtdel',
            },
            {
                'args': (
                    'Court of Common Pleas  Hartford County',
                    'asdf',
                ),
                'answer': 'connsuperct'
            },
        )
        for d in pairs:
            got = get_state_court_object(*d['args'])
            self.assertEqual(
                got,
                d['answer'],
                msg="\nDid not get court we expected: '%s'.\n"
                    "               Instead we got: '%s'" % (d['answer'], got)
            )

    def test_get_fed_court_object_from_string(self):
        """Can we get the correct federal courts?"""

        pairs = (
            {
                'q': 'Eastern District of New York',
                'a': 'nyed'
            },
            {
                'q': 'Northern District of New York',
                'a': 'nynd'
            },
            {
                'q':  'Southern District of New York',
                'a': 'nysd'
            },
            # When we have unknown first word, we assume it's errant.
            {
                'q': 'Nathan District of New York',
                'a': 'nyd'
            },
            {
                'q': "Nate District of New York",
                'a': 'nyd',
            },
            {
                'q': "Middle District of Pennsylvania",
                'a': 'pamd',
            },
            {
                'q': "Middle Dist. of Pennsylvania",
                'a': 'pamd',
            },
            {
                'q': "M.D. of Pennsylvania",
                'a': 'pamd',
            }
        )
        for test in pairs:
            print("Testing: %s, expecting: %s" % (test['q'], test['a']))
            got = match_court_string(test['q'], federal_district=True)
            self.assertEqual(
                test['a'],
                got,
            )

    def test_get_appellate_court_object_from_string(self):
        """Can we get the correct federal appellate courts?"""

        pairs = (
            {
                # FJC data appears to have a space between U and S.
                'q': 'U. S. Court of Appeals for the Ninth Circuit',
                'a': 'ca9',
            },
            {
                'q': 'U.S. Court of Appeals for the Ninth Circuit',
                'a': 'ca9',
            },
        )
        for test in pairs:
            print("Testing: %s, expecting: %s" % (test['q'], test['a']))
            got = match_court_string(test['q'], federal_appeals=True)
            self.assertEqual(test['a'], got)


@pytest.mark.django_db
class PacerDocketParserTest(TestCase):
    """Can we parse RECAP dockets successfully?"""
    NUM_PARTIES = 3
    NUM_PETRO_ATTYS = 6
    NUM_FLOYD_ROLES = 3
    NUM_DOCKET_ENTRIES = 123
    DOCKET_PATH = os.path.join(settings.MEDIA_ROOT, 'test', 'xml',
                               'gov.uscourts.akd.41664.docket.xml')

    def setUp(self):

        self.docket, count = find_docket_object('akd', '41664',
                                                '3:11-cv-00064')
        if count > 1:
            raise Exception("Should not get more than one docket during "
                            "this test!")
        process_docket_data(self.docket, self.DOCKET_PATH,
                            UPLOAD_TYPE.IA_XML_FILE)

    def tearDown(self):
        Docket.objects.all().delete()
        Party.objects.all().delete()
        Attorney.objects.all().delete()
        AttorneyOrganization.objects.all().delete()

    def test_docket_entry_parsing(self):
        """Do we get the docket entries we expected?"""
        # Total count is good?
        all_rds = RECAPDocument.objects.all()
        self.assertEqual(self.NUM_DOCKET_ENTRIES, all_rds.count())

        # Main docs exist and look about right?
        rd = RECAPDocument.objects.get(pacer_doc_id='0230856334')
        desc = rd.docket_entry.description
        good_de_desc = all([
            desc.startswith("COMPLAINT"),
            'Filing fee' in desc,
            desc.endswith("2011)"),
        ])
        self.assertTrue(good_de_desc)

        # Attachments have good data?
        att_rd = RECAPDocument.objects.get(pacer_doc_id='02301132632')
        self.assertTrue(all([
            att_rd.description.startswith('Judgment'),
            "redistributed" in att_rd.description,
            att_rd.description.endswith("added"),
        ]), "Description didn't match. Got: %s" % att_rd.description)
        self.assertEqual(att_rd.attachment_number, 1)
        self.assertEqual(att_rd.document_number, '116')
        self.assertEqual(att_rd.docket_entry.date_filed, date(2012, 12, 10))

        # Two documents under the docket entry?
        self.assertEqual(att_rd.docket_entry.recap_documents.all().count(), 2)

    def test_party_parsing(self):
        """Can we parse an XML docket and get good results in the DB"""
        self.assertEqual(self.docket.parties.all().count(), self.NUM_PARTIES)

        petro = self.docket.parties.get(name__contains="Petro")
        self.assertEqual(petro.party_types.all()[0].name, "Plaintiff")

        attorneys = petro.attorneys.all().distinct()
        self.assertEqual(attorneys.count(), self.NUM_PETRO_ATTYS)

        floyd = petro.attorneys.distinct().get(name__contains='Floyd')
        self.assertEqual(floyd.roles.all().count(), self.NUM_FLOYD_ROLES)
        self.assertEqual(floyd.name, u'Floyd G. Short')
        self.assertEqual(floyd.email, u'fshort@susmangodfrey.com')
        self.assertEqual(floyd.fax, u'(206) 516-3883')
        self.assertEqual(floyd.phone, u'(206) 373-7381')

        godfrey_llp = floyd.organizations.all()[0]
        self.assertEqual(godfrey_llp.name, u'Susman Godfrey, LLP')
        self.assertEqual(godfrey_llp.address1, u'1201 Third Ave.')
        self.assertEqual(godfrey_llp.address2, u'Suite 3800')
        self.assertEqual(godfrey_llp.city, u'Seattle')
        self.assertEqual(godfrey_llp.state, u'WA')


class GetQuarterTest(unittest.TestCase):
    """Can we properly figure out when the quarter that we're currently in
    began?
    """

    def test_january(self):
        self.assertEqual(
            date(2018, 1, 1),
            get_start_of_quarter(date(2018, 1, 1))
        )
        self.assertEqual(
            date(2018, 1, 1),
            get_start_of_quarter(date(2018, 1, 10))
        )

    def test_december(self):
        self.assertEqual(
            date(2018, 10, 1),
            get_start_of_quarter(date(2018, 12, 1))
        )


@pytest.mark.django_db
class IAUploaderTest(TestCase):
    """Tests related to uploading docket content to the Internet Archive"""

    fixtures = ['test_objects_query_counts.json',
                'attorney_party_dup_roles.json']

    def test_correct_json_generated(self):
        """Do we generate the correct JSON for a handful of tricky dockets?

        The most important thing here is that we don't screw up how we handle
        m2m relationships, which have a tendency of being tricky.
        """
        d, j_str = generate_ia_json(1)
        j = json.loads(j_str)
        parties = j['parties']
        first_party = parties[0]
        first_party_attorneys = first_party['attorneys']
        expected_num_attorneys = 1
        actual_num_attorneys = len(first_party_attorneys)
        self.assertEqual(
            expected_num_attorneys,
            actual_num_attorneys,
            msg="Got wrong number of attorneys when making IA JSON. "
                "Got %s, expected %s: \n%s" % (actual_num_attorneys,
                                               expected_num_attorneys,
                                               first_party_attorneys)
        )

        first_attorney = first_party_attorneys[0]
        attorney_roles = first_attorney['roles']
        expected_num_roles = 1
        actual_num_roles = len(attorney_roles)
        self.assertEqual(
            actual_num_roles,
            expected_num_roles,
            msg="Got wrong number of roles on attorneys when making IA JSON. "
                "Got %s, expected %s" % (actual_num_roles, expected_num_roles)
        )

    def test_num_queries_ok(self):
        """Have we regressed the number of queries it takes to make the JSON

        It's very easy to use the DRF in a way that generates a LOT of queries.
        Let's avoid that.
        """
        with self.assertNumQueries(10):
            generate_ia_json(1)

        with self.assertNumQueries(4):
            generate_ia_json(2)

        with self.assertNumQueries(4):
            generate_ia_json(3)
