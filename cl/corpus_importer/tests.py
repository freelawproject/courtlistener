# coding=utf-8
import os
from datetime import date

from django.conf import settings
from django.test import TestCase

from cl.corpus_importer.dup_helpers import case_name_in_candidate
from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.corpus_importer.import_columbia.parse_opinions import \
    get_state_court_object
from cl.corpus_importer.lawbox.judge_extractor import get_judge_from_str, \
    REASONS
from cl.lib.pacer import process_docket_data
from cl.people_db.import_judges.populate_fjc_judges import get_fed_court_object
from cl.people_db.models import Attorney, AttorneyOrganization, Party
from cl.recap.tasks import find_docket_object
from cl.recap.models import IA_XML_FILE
from cl.search.models import Docket, RECAPDocument


class JudgeExtractionTest(TestCase):
    def test_extracting_judges_from_strings_lawbox(self):
        pairs = (
            ('The following is the order of Judge Brailsford',
             (u'Brailsford', REASONS[12])),
            ('Before INGRAHAM, Circuit Judge, and SEALS and COWAN, District '
             'Judges.',
             (u'Ingraham, Circuit Judge, and Seals and Cowan, District Judges',
              REASONS[14])),
            ('J. H. Reddy, Chattanooga, Tenn., James F. Neal, John J. Hooker, '
             'Sr., Special Atty., Nashville, Tenn., Charles W. Shaffer, Jr., '
             'Dept. of Justice, Washington, D. C., for the United States.',
             (None, REASONS[10])),
            ('MR. JUSTICE CLARK delivered the opinion of the Court.',
             (u'Clark', REASONS[5])),
            ('Justice THEIS delivered the judgment of the court, '
             'with opinion.',
             (u'Theis', REASONS[5])),
            ('Kennedy, J., announced the judgment of the Court and delivered '
             'the opinion of the Court, except...',
             (u'Kennedy', REASONS[5])),
            ('Kendy, J., announced the judgment of the Court ',
             (u'Kendy', REASONS[5])),
            ('U.S.C. 22, JUSTICE Eats Apples', (None, REASONS[3])),
            # Has a judiciary word, but not at the end.
            ('PER CURIAM', (u'Per Curiam', REASONS[6])),
            ('Per Curiam', (u'Per Curiam', REASONS[6])),
            ('L. CHANDLER WATSON, Jr., Bankruptcy Judge.',
             (u'L. Chandler Watson, Jr.', REASONS[7])),
            ('VOLINN, Bankruptcy Judge:', (u'Volinn', REASONS[7])),
            ('McGOVERN, District Judge.', (u'McGovern', REASONS[7])),
            ('JOHN TeSELLE, Bankruptcy Judge.', (u'John Teselle', REASONS[7])),
            ('LEAPHART, Justice', (u'Leaphart', REASONS[7])),
            ('SIMPSON, C.J.', (u'Simpson', REASONS[7])),
            ('LANSING, Judge.', (u'Lansing', REASONS[7])),
            ('BRAUN, PLAINTIFF, Kendrick, Finkbeiner, Schafer & Murphy (by '
             'Michael J. W. Horn), for defendants.',
             (None, REASONS[4])),
            ('OPINION BY MR. JUSTICE JONES, May 25953',
             (u'Mr. Justice Jones', REASONS[8])),
            ('Opinion by Justice ROSS', (u'Ross', REASONS[8])),
            ('SPENCE, J.', (u'Spence', REASONS[7])),
            ('Spencer, J.,', (u'Spencer', REASONS[7])),
            ('SPENCE', (None, REASONS[9])),
            ('Nourse, P. J.', (u'Nourse', REASONS[7])),
            ('A. SPENCE, J.', (u'A. Spence', REASONS[7])),
            ('Van SICKLE, District Judge.', (u'Van Sickle', REASONS[7])),
            ('VanSICKLE, District Judge.', (u'Vansickle', REASONS[7])),
            ('LeGRAND, Justice.', (u'Legrand', REASONS[7])),
            ('DAVID R. STRAWBRIDGE; United States Magistrate Judge.',
             (u'David R. Strawbridge', REASONS[7])),
            ('CARRICO, J., delivered the opinion of the court.',
             (u'Carrico', REASONS[5])),
            ('Justice HARTMAN delivered the opinion of the court',
             (u'Hartman', REASONS[5])),
            ('Justice APPLETON delivered the opinion of the court',
             (u'Appleton', REASONS[5])),
            ('The opinion of the Court was delivered by HANDLER, J.',
             (u'Handler', REASONS[11])),
            ('The following is the order of Judge Brailsford',
             (u'Brailsford', REASONS[12])),
            ('Before: NEFF, P.J., and MICHAEL J. KELLY and HOOD, JJ.',
             (u'Neff, P.J., and Michael J. Kelly and Hood', REASONS[14])),
            ('Chief Judge FULD', (u'Fuld', REASONS[15])),
            ('FOTH, C.', (u'Foth', REASONS[7])),
            ('Robert L. KRECHEVSKY, Bankruptcy Judge.',
             (u'Robert L. Krechevsky', REASONS[7])),
            ('Ernstrom & Dreste, Rochester, NY (J. William Ernstrom, of '
             'counsel), for Northland Associates, Inc.',
             (None, REASONS[10])),

            # memorandum looks like a bad_word, but it's not
            ('BREITEL and Judge JASEN, GABRIELLI, JONES, WACHTLER and COOKE '
             'Concur in Memorandum',
             (u'Breitel and Judge Jasen, Gabrielli, Jones, Wachtler and Cooke '
              u'Concur in Memorandum', REASONS[16])),
            # but if it starts with Memorandum, it's no good.
            ('Memorandum of Decision on R.C. Allen Instruments',
             (None, REASONS[10])),
            ('CONCLUDING That the Aggravating Circumstances Outweighed the '
             'Mitigating Circumstances.',
             (None, REASONS[4])),
            ('Considering Factor (A), "The Ultimate and Decisive Test," We '
             'Examine Factors (E), (F) and (H)',
             (None, REASONS[10])),
            ('Decision Denying Application to Retain Rebecca J. Habbert',
             (None, REASONS[10])),
            ("Accepting Appellant's Pleas of Guilty, the Record Reflects the "
             "Following Occurred:",
             (None, REASONS[10])),
            ('ADDRESSING Ourselves to the Substance of These Questions We '
             'Think It Appropriate',
             (None, REASONS[4])),
            ('ADMITTING a Statement as a Dying Declaration, the Trial Court '
             'Must Make a Preliminary',
             (None, REASONS[4])),
            ('AMENDED Findings of Fact', (None, REASONS[4])),
            ('AMICUS Curiae Brief Was Filed by Bruce A. Olsen',
             (None, REASONS[4])),
            ('LAWRENCE S. Robbins Argued the Cause for Appellants. With Him',
             (None, REASONS[4])),
            ('DISCUSSING These Cases We Must Separate Them According to The',
             (None, REASONS[4])),
            ('EXAMINING These and the Other Defenses Which Comdisco Has '
             'Raised, However',
             (None, REASONS[4])),
            ('GOING Into the Question of the Public', (None, REASONS[4])),
            # Going is bad, but foregoing is good
            ('JUDGE BLATCHFORD After Stating the Facts in the Foregoing '
             'Language',
             (u'Judge Blatchford', REASONS[7])),
            ('DECISION Granting Judgment to the Trustee in Bankruptcy for '
             'Comprehensive Business Systems',
             (None, REASONS[4])),
            ('THESE Arguments That Both Sides Would Be Allowed Wide Latitude '
             'in Arguing',
             (None, REASONS[4])),
            ('DECISION Denying Application to Retain Rebecca J. Habbert',
             (None, REASONS[4])),
            ('TRIAL, Appellant Argued That It Was a Third-Party Benefic',
             (None, REASONS[4])),
            ('FINDINGS of Fact and Conclusion of Law on Eastgroup',
             (None, REASONS[4])),
            ('PROCEEDING Further a General Description of the Area Will Be '
             'Helpful',
             (None, REASONS[4])),
            ('TURNING Them Over to His Counsel on the Morning of July 24',
             (None, REASONS[4])),
            # Starting with a number.
            ('1975, SECTION 594 Did Not Describe What Kind judge ',
             (None, REASONS[3])),
            # Starting with a regex special char
            ('("DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            ('"DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            (':"DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            ('>"DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            ('["DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            ('{"DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            ('}"DGCL") SEEKING judge Advancement of Reasonable Attorney\'s '
             'Fees',
             (None, REASONS[3])),
            # Starts with "The", but is a valid form
            ('The Cause Was Argued Before Anderson', (u'Anderson',
                                                      REASONS[17])),
            # Lowercase 'the' is no good, however
            ('the Water Heater Was Installed, the Slates, j.',
             (None, REASONS[18])),
            # Starting with "There " is no good, but "Theresa" is
            ('THERE is No Merit in the Claim of Improper Comment of the '
             'Commonwealth, J.',
             (None, REASONS[3])),
            ('THERESA CRAFT, J.', (u'Theresa Craft', REASONS[7])),
            # Nothing with utf-8 as first char is good.
            (u'\xe2\xa7\xe2\xa7 19-1-102(1), JUDGE', (None, REASONS[2])),
            # Argued Before is ok, but Argued is not.
            ('Argued before Lissner', (u'Lissner', REASONS[17])),
            ('ARGUED: amy louise howe, before so-and-so, Justice',
             (None, REASONS[3])),
        )

        for q, a in pairs:
            self.assertEqual(tuple(get_judge_from_str(q)), a)

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


class CaseNameMatchTest(TestCase):
    def test_pairs(self):
        pairs = (
            (('Testacular', 'Testacular'), True),
            (("Ass'n Managers v. Lissner", 'Association Managers v. Lissner'),
             False),
        )

        for q, a in pairs:
            self.assertEqual(case_name_in_candidate(*q), a)


class CourtMatchingTest(TestCase):
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
            print "Testing: %s, expecting: %s" % (test['q'], test['a'])
            got = get_fed_court_object(test['q'])
            self.assertEqual(
                test['a'],
                got,
            )


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
        process_docket_data(self.docket, self.DOCKET_PATH, IA_XML_FILE)

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
