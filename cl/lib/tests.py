# coding=utf8
from __future__ import print_function

import datetime
import os
import re
import tempfile

from django.core.files.base import ContentFile
from django.urls import reverse
from django.test import TestCase, SimpleTestCase
from django.test import override_settings
from rest_framework.status import HTTP_503_SERVICE_UNAVAILABLE, HTTP_200_OK

from cl.lib.db_tools import queryset_generator
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.mime_types import lookup_mime_type
from cl.lib.model_helpers import make_upload_path, make_docket_number_core
from cl.lib.pacer import normalize_attorney_role, normalize_attorney_contact, \
    normalize_us_state, make_address_lookup_key, get_blocked_status
from cl.lib.search_utils import make_fq
from cl.lib.storage import UUIDFileSystemStorage
from cl.lib.string_utils import trunc, anonymize
from cl.people_db.models import Role
from cl.scrapers.models import UrlHash
from cl.search.models import Opinion, OpinionCluster, Docket, Court


class TestPacerUtils(TestCase):
    fixtures = ['court_data.json']

    def test_auto_blocking_small_bankr_docket(self):
        """Do we properly set small bankruptcy dockets to private?"""
        d = Docket()
        d.court = Court.objects.get(pk='akb')
        blocked, date_blocked = get_blocked_status(d)
        self.assertTrue(blocked, msg="Bankruptcy dockets with few entries "
                                     "should be blocked.")
        blocked, date_blocked = get_blocked_status(d, count_override=501)
        self.assertFalse(blocked, msg="Bankruptcy dockets with many entries "
                                      "should not be blocked")
        # This should stay blocked even though it's a big bankruptcy docket.
        d.blocked = True
        blocked, date_blocked = get_blocked_status(d, count_override=501)
        self.assertTrue(blocked, msg="Bankruptcy dockets that start blocked "
                                     "should stay blocked.")


class TestDBTools(TestCase):
    # This fixture uses UrlHash objects b/c they've been around a long while and
    # are wickedly simple objects.
    fixtures = ['test_queryset_generator.json']

    def test_queryset_generator(self):
        """Does the generator work properly with a variety of queries?"""
        tests = [
            {'query': UrlHash.objects.filter(pk__in=['BAD ID']),
             'count': 0},
            {'query': UrlHash.objects.filter(pk__in=['0']),
             'count': 1},
            {'query': UrlHash.objects.filter(pk__in=['0', '1']),
             'count': 2},
        ]
        for test in tests:
            print("Testing queryset_generator with %s expected results..." %
                  test['count'], end='')
            count = 0
            for _ in queryset_generator(test['query']):
                count += 1
            self.assertEqual(count, test['count'])
            print('✓')

    def test_queryset_generator_values_query(self):
        """Do values queries work?"""
        print("Testing raising an error when we can't get a PK in a values "
              "query...", end='')
        self.assertRaises(
            Exception,
            queryset_generator(UrlHash.objects.values('sha1')),
            msg="Values query did not fail when pk was not provided."
        )
        print('✓')

        print("Testing a good values query...", end='')
        self.assertEqual(
            sum(1 for _ in queryset_generator(UrlHash.objects.values())),
            2,
        )
        print('✓')

    def test_queryset_generator_chunking(self):
        """Does chunking work properly without duplicates or omissions?"""
        print("Testing if queryset_iterator chunking returns the right "
              "number of results...", end='')
        expected_count = 2
        results = queryset_generator(UrlHash.objects.all(), chunksize=1)
        self.assertEqual(
            expected_count,
            sum(1 for _ in results),
        )
        print('✓')


class TestStringUtils(TestCase):
    def test_trunc(self):
        """Does trunc give us the results we expect?"""
        s = 'Henry wants apple.'
        tests = (
            # Simple case
            {'length': 13, 'result': 'Henry wants'},
            # Off by one cases
            {'length': 4, 'result': 'Henr'},
            {'length': 5, 'result': 'Henry'},
            {'length': 6, 'result': 'Henry'},
            # Do we include the length of the ellipsis when measuring?
            {'length': 12, 'ellipsis': '...', 'result': 'Henry...'},
            # What happens when an alternate ellipsis is used instead?
            {'length': 15, 'ellipsis': '....', 'result': 'Henry wants....'},
            # Do we cut properly when no spaces are found?
            {'length': 2, 'result': 'He'},
            # Do we cut properly when ellipsizing if no spaces found?
            {'length': 6, 'ellipsis': '...', 'result': 'Hen...'},
            # Do we return the whole s when length >= s?
            {'length': 50, 'result': s}
        )
        for test_dict in tests:
            result = trunc(
                s=s,
                length=test_dict['length'],
                ellipsis=test_dict.get('ellipsis', None),
            )
            self.assertEqual(
                result,
                test_dict['result'],
                msg='Failed with dict: %s.\n'
                    '%s != %s' % (test_dict, result, test_dict['result'])
            )
            self.assertTrue(
                len(result) <= test_dict['length'],
                msg="Failed with dict: %s.\n"
                    "%s is longer than %s" %
                    (test_dict, result, test_dict['length'])
            )

    def test_anonymize(self):
        """Can we properly anonymize SSNs, EINs, and A-Numbers?"""
        # Simple cases. Anonymize them.
        self.assertEqual(anonymize('111-11-1111'), ('XXX-XX-XXXX', True))
        self.assertEqual(anonymize('11-1111111'), ('XX-XXXXXXX', True))
        self.assertEqual(anonymize('A11111111'), ('AXXXXXXXX', True))
        self.assertEqual(anonymize('A111111111'), ('AXXXXXXXX', True))

        # Starting or ending with letters isn't an SSN
        self.assertEqual(anonymize('A111-11-1111'), ('A111-11-1111', False))
        self.assertEqual(anonymize('111-11-1111A'), ('111-11-1111A', False))

        # Matches in a sentence
        self.assertEqual(
            anonymize('Term 111-11-1111 Term'),
            ('Term XXX-XX-XXXX Term', True),
        )
        self.assertEqual(
            anonymize('Term 11-1111111 Term'),
            ('Term XX-XXXXXXX Term', True),
        )
        self.assertEqual(
            anonymize('Term A11111111 Term'),
            ('Term AXXXXXXXX Term', True),
        )

        # Multiple matches
        self.assertEqual(
            anonymize("Term 111-11-1111 Term 111-11-1111 Term"),
            ('Term XXX-XX-XXXX Term XXX-XX-XXXX Term', True),
        )


class TestMakeFQ(TestCase):
    def test_make_fq(self):
        test_pairs = (
            ('1 2', '1 AND 2'),
            ('1 and 2', '1 AND 2'),
            ('"1 AND 2"', '"1 AND 2"'),
            ('"1 2"', '"1 2"'),
            ('1 OR 2', '1 OR 2'),
            ('1 NOT 2', '1 NOT 2'),
            ('cause:sympathy', 'cause AND sympathy')
        )
        for test in test_pairs:
            field = 'f'
            key = 'key'
            self.assertEqual(
                make_fq(cd={key: test[0]}, field=field, key=key),
                '%s:(%s)' % (field, test[1])
            )


class TestModelHelpers(TestCase):
    """Test the model_utils helper functions"""
    fixtures = ['test_court.json']

    def setUp(self):
        self.court = Court.objects.get(pk='test')
        self.docket = Docket(case_name=u'Docket', court=self.court)
        self.opinioncluster = OpinionCluster(
            case_name=u'Hotline Bling',
            docket=self.docket,
            date_filed=datetime.date(2015, 12, 14),
        )
        self.opinion = Opinion(
            cluster=self.opinioncluster,
            type='Lead Opinion',
        )

    def test_make_upload_path_works_with_opinions(self):
        expected = 'mp3/2015/12/14/hotline_bling.mp3'
        self.opinion.file_with_date = datetime.date(2015, 12, 14)
        path = make_upload_path(self.opinion, 'hotline_bling.mp3')
        self.assertEqual(expected, path)

    def test_making_docket_number_core(self):
        expected = '1201032'
        self.assertEqual(make_docket_number_core('2:12-cv-01032-JKG-MJL'),
                         expected)
        self.assertEqual(make_docket_number_core('12-cv-01032-JKG-MJL'),
                         expected)
        self.assertEqual(make_docket_number_core('2:12-cv-01032'),
                         expected)
        self.assertEqual(make_docket_number_core('12-cv-01032'),
                         expected)

        # Do we automatically zero-pad short docket numbers?
        self.assertEqual(make_docket_number_core('12-cv-1032'),
                         expected)
        # Do we skip appellate courts?
        self.assertEqual(make_docket_number_core('12-01032'), '')
        # docket_number fields can be null. If so, the core value should be
        # an empty string.
        self.assertEqual(make_docket_number_core(None), '')


class UUIDFileSystemStorageTest(SimpleTestCase):
    # Borrows from https://github.com/django/django/blob/9cbf48693dcd8df6cb22c183dcc94e7ce62b2921/tests/file_storage/tests.py#L89
    allow_database_queries = True

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = UUIDFileSystemStorage(location=self.temp_dir,
                                             base_url='test_uuid_storage')

    def test_file_save_with_path(self):
        """Does saving a pathname create directories and filenames correctly?"""
        self.assertFalse(self.storage.exists('path/to'))
        file_name = 'filename'
        extension = 'ext'
        f = self.storage.save('path/to/%s.%s' % (file_name, extension),
                              ContentFile('file with path'))
        self.assertTrue(self.storage.exists('path/to'))
        dir_name_created, file_name_created = os.path.split(f)
        file_root_created, extension_created = file_name_created.split('.', 1)
        self.assertEqual(extension_created, extension)
        self.assertTrue(re.match('[a-f0-9]{32}', file_root_created))


class TestMimeLookup(TestCase):
    """ Test the Mime type lookup function(s)"""

    def test_unsupported_extension_returns_octetstream(self):
        """ For a bad extension, do we return the proper default? """
        tests = [
            '/var/junk/filename.something.xyz',
            '../var/junk/~filename_something',
            '../../junk.junk.xxx'
        ]
        for test in tests:
            self.assertEqual('application/octet-stream', lookup_mime_type(test))

    def test_known_good_mimetypes(self):
        """ For known good mimetypes, make sure we return the right value """
        tests = {
            'mp3/2015/1/1/something_v._something_else.mp3': 'audio/mpeg',
            'doc/2015/1/1/voutila_v._bonvini.doc': 'application/msword',
            'pdf/2015/1/1/voutila_v._bonvini.pdf': 'application/pdf',
            'txt/2015/1/1/voutila_v._bonvini.txt': 'text/plain',
        }
        for test_path in tests.keys():
            self.assertEqual(tests.get(test_path), lookup_mime_type(test_path))


@override_settings(MAINTENANCE_MODE_ENABLED=True)
class TestMaintenanceMiddleware(TestCase):
    """ Test the maintenance middleware """
    fixtures = ['authtest_data.json']

    def test_middleware_works_when_enabled(self):
        """ Does the middleware block users when enabled? """
        r = self.client.get(reverse('show_results'))
        self.assertEqual(
            r.status_code,
            HTTP_503_SERVICE_UNAVAILABLE,
            'Did not get correct status code. Got: %s instead of %s' % (
                r.status_code,
                HTTP_503_SERVICE_UNAVAILABLE,
            )
        )

    def test_staff_can_get_through(self):
        """ Can staff get through when the middleware is enabled? """
        self.assertTrue(self.client.login(
            username='admin', password='password'))
        r = self.client.get(reverse('show_results'))
        self.assertEqual(
            r.status_code,
            HTTP_200_OK,
            'Staff did not get through, but should have. Staff got status code '
            'of: %s instead of %s' % (r.status_code, HTTP_200_OK)
        )


class TestPACERPartyParsing(TestCase):
    """Various tests for the PACER party parsers."""

    def test_attorney_role_normalization(self):
        """Can we normalize the attorney roles into a small number of roles?"""
        pairs = [{
            'q': '(Inactive)',
            'a': {'role': Role.INACTIVE,
                  'date_action': None,
                  'role_raw': '(Inactive)'},
        }, {
            'q': 'ATTORNEY IN SEALED GROUP',
            'a': {'role': Role.ATTORNEY_IN_SEALED_GROUP,
                  'date_action': None,
                  'role_raw': 'ATTORNEY IN SEALED GROUP'},
        }, {
            'q': 'ATTORNEY TO BE NOTICED',
            'a': {'role': Role.ATTORNEY_TO_BE_NOTICED,
                  'date_action': None,
                  'role_raw': 'ATTORNEY TO BE NOTICED'},
        }, {
            'q': 'Bar Status: ACTIVE',
            'a': {'role': None,
                  'date_action': None,
                  'role_raw': 'Bar Status: ACTIVE'},
        }, {
            'q': 'DISBARRED 02/19/2010',
            'a': {'role': Role.DISBARRED,
                  'date_action': datetime.date(2010, 2, 19),
                  'role_raw': 'DISBARRED 02/19/2010'},
        }, {
            'q': 'Designation: ADR Pro Bono Limited Scope Counsel',
            'a': {'role': None,
                  'date_action': None,
                  'role_raw': 'Designation: ADR Pro Bono Limited Scope '
                              'Counsel'},
        }, {
            'q': 'LEAD ATTORNEY',
            'a': {'role': Role.ATTORNEY_LEAD,
                  'date_action': None,
                  'role_raw': 'LEAD ATTORNEY'},
        }, {
            'q': 'PRO HAC VICE',
            'a': {'role': Role.PRO_HAC_VICE,
                  'date_action': None,
                  'role_raw': 'PRO HAC VICE'},
        }, {
            'q': 'SELF- TERMINATED: 01/14/2013',
            'a': {'role': Role.SELF_TERMINATED,
                  'date_action': datetime.date(2013, 1, 14),
                  'role_raw': 'SELF- TERMINATED: 01/14/2013'},
        }, {
            'q': 'SUSPENDED 01/22/2016',
            'a': {'role': Role.SUSPENDED,
                  'date_action': datetime.date(2016, 1, 22),
                  'role_raw': 'SUSPENDED 01/22/2016'},
        }, {
            'q': 'TERMINATED: 01/01/2007',
            'a': {'role': Role.TERMINATED,
                  'date_action': datetime.date(2007, 1, 1),
                  'role_raw': 'TERMINATED: 01/01/2007'},
        }, {
            'q': 'Blagger jabber',
            'a': {'role': None,
                  'date_action': None,
                  'role_raw': 'Blagger jabber'},
        }]
        for pair in pairs:
            print("Normalizing PACER role of '%s' to '%s'..." %
                  (pair['q'], pair['a']), end='')
            result = normalize_attorney_role(pair['q'])
            self.assertEqual(result, pair['a'])
            print('✓')

    def test_state_normalization(self):
        pairs = [{
            'q': 'CA',
            'a': 'CA',
        }, {
            'q': 'ca',
            'a': 'CA',
        }, {
            'q': 'California',
            'a': 'CA',
        }, {
            'q': 'california',
            'a': 'CA',
        }]
        for pair in pairs:
            print("Normalizing state of '%s' to '%s'..." %
                  (pair['q'], pair['a']), end='')
            result = normalize_us_state(pair['q'])
            self.assertEqual(result, pair['a'])
            print('✓')

    def test_normalize_atty_contact(self):
        pairs = [{
            # Email and phone number
            'q': "Landye Bennett Blumstein LLP\n"
                 "701 West Eighth Avenue, Suite 1200\n"
                 "Anchorage, AK 99501\n"
                 "907-276-5152\n"
                 "Email: brucem@lbblawyers.com",
            'a': ({
                'name': u"Landye Bennett Blumstein LLP",
                'address1': u'701 West Eighth Ave.',
                'address2': u'Suite 1200',
                'city': u'Anchorage',
                'state': u'AK',
                'zip_code': u'99501',
                'lookup_key': u'701westeighthavesuite1200anchoragelandyebennettblumsteinak99501',
            }, {
                'email': u'brucem@lbblawyers.com',
                'phone': u'(907) 276-5152',
                'fax': u'',
            })
        }, {
            # PO Box
            'q': "Sands Anderson PC\n"
                 "P.O. Box 2188\n"
                 "Richmond, VA 23218-2188\n"
                 "(804) 648-1636",
            'a': ({
                'name': u'Sands Anderson PC',
                'address1': u'P.O. Box 2188',
                'city': u'Richmond',
                'state': u'VA',
                'zip_code': u'23218-2188',
                'lookup_key': u'pobox2188richmondsandsandersonva232182188',
            }, {
                'phone': u'(804) 648-1636',
                'fax': u'',
                'email': u'',
            })
        }, {
            # Lowercase state (needs normalization)
            'q': "Sands Anderson PC\n"
                 "P.O. Box 2188\n"
                 "Richmond, va 23218-2188\n"
                 "(804) 648-1636",
            'a': ({
                'name': u'Sands Anderson PC',
                'address1': u'P.O. Box 2188',
                'city': u'Richmond',
                'state': u'VA',
                'zip_code': u'23218-2188',
                'lookup_key': u'pobox2188richmondsandsandersonva232182188',
            }, {
                'phone': u"(804) 648-1636",
                'fax': u'',
                'email': u'',
            })
        }, {
            # Phone, fax, and email -- the whole package.
            'q': "Susman Godfrey, LLP\n"
                 "1201 Third Avenue, Suite 3800\n"
                 "Seattle, WA 98101\n"
                 "206-373-7381\n"
                 "Fax: 206-516-3883\n"
                 "Email: fshort@susmangodfrey.com",
            'a': ({
                'name': u'Susman Godfrey, LLP',
                'address1': u'1201 Third Ave.',
                'address2': u'Suite 3800',
                'city': u'Seattle',
                'state': u'WA',
                'zip_code': u'98101',
                'lookup_key': u'1201thirdavesuite3800seattlesusmangodfreywa98101',
            }, {
                'phone': u'(206) 373-7381',
                'fax': u'(206) 516-3883',
                'email': u'fshort@susmangodfrey.com',
            })
        }, {
            # No recipient name
            'q': "211 E. Livingston Ave\n"
                 "Columbus, OH 43215\n"
                 "(614) 228-3727\n"
                 "Email:",
            'a': ({
                'address1': u'211 E. Livingston Ave',
                'city': u'Columbus',
                'state': u'OH',
                'zip_code': u'43215',
                'lookup_key': u'211elivingstonavecolumbusoh43215',
            }, {
                'phone': u'(614) 228-3727',
                'email': u'',
                'fax': u'',
            }),
        }, {
            # Weird ways of doing phone numbers
            'q': """1200 Boulevard Tower
                    1018 Kanawha Boulevard, E
                    Charleston, WV 25301
                    304/342-3174
                    Fax: 304/342-0448
                    Email: caglelaw@aol.com
                """,
            'a': ({
                'address1': u'1018 Kanawha Blvd., E',
                'address2': u'1200 Blvd. Tower',
                'city': u'Charleston',
                'state': u'WV',
                'zip_code': u'25301',
                'lookup_key': u'1018kanawhablvde1200blvdtowercharlestonwv25301',
            }, {
                'phone': '(304) 342-3174',
                'fax': '(304) 342-0448',
                'email': 'caglelaw@aol.com',
            })
        }, {
            # Empty fax numbers (b/c PACER).
            'q': """303 E 17th Ave
                    Suite 300
                    Denver, CO 80203
                    303-861-1764
                    Fax:
                    Email: jeff@dyerberens.com
            """,
            'a': ({
                'address1': u'303 E 17th Ave',
                'address2': u'Suite 300',
                'city': u'Denver',
                'state': u'CO',
                'zip_code': u'80203',
                'lookup_key': u'303e17thavesuite300denverco80203',
            }, {
                'phone': u'(303) 861-1764',
                'fax': u'',
                'email': u'jeff@dyerberens.com',
            })
        }, {
            # Funky phone number
            'q': """Guerrini Law Firm
                    106 SOUTH MENTOR AVE. #150
                    Pasadena, CA 91106
                    626-229-9611-202
                    Fax: 626-229-9615
                    Email: guerrini@guerrinilaw.com
                """,
            'a': ({
                'name': u'Guerrini Law Firm',
                'address1': u'106 South Mentor Ave.',
                'address2': u'# 150',
                'city': u'Pasadena',
                'state': u'CA',
                'zip_code': u'91106',
                'lookup_key': u'106southmentorave150pasadenaguerrinilawfirmca91106',
            }, {
                'phone': u'',
                'fax': u'(626) 229-9615',
                'email': u'guerrini@guerrinilaw.com',
            })
        }, {
            'q': """Duncan & Sevin, LLC
                    400 Poydras St.
                    Suite 1200
                    New Orleans, LA 70130
                """,
            'a': ({
                'name': u'Duncan & Sevin, LLC',
                'address1': u'400 Poydras St.',
                'address2': u'Suite 1200',
                'city': u'New Orleans',
                'state': u'LA',
                'zip_code': u'70130',
                'lookup_key': u'400poydrasstsuite1200neworleansduncansevinllcla70130',
            }, {
                'phone': u'',
                'fax': u'',
                'email': u'',
            })
        }, {
            # Ambiguous address. Returns empty dict.
            'q': """Darden, Koretzky, Tessier, Finn, Blossman & Areaux
                    Energy Centre
                    1100 Poydras Street
                    Suite 3100
                    New Orleans, LA 70163
                    504-585-3800
                    Email: darden@carverdarden.com
                """,
            'a': ({}, {
                'phone': u'(504) 585-3800',
                'email': u'darden@carverdarden.com',
                'fax': u'',
            })
        }, {
            # Ambiguous address with unicode that triggers
            # https://github.com/datamade/probableparsing/issues/2
            'q': u"""Darden, Koretzky, Tessier, Finn, Blossman & Areaux
                    Energy Centre
                    1100 Poydras Street
                    Suite 3100
                    New Orléans, LA 70163
                    504-585-3800
                    Email: darden@carverdarden.com
                """,
            'a': ({}, {
                'phone': u'(504) 585-3800',
                'email': u'darden@carverdarden.com',
                'fax': u'',
            })
        }, {
            # Missing zip code, phone number ambiguously used instead.
            'q': """NSB - Department of Law
                    POB 69
                    Barrow, AK 907-852-0300
                """,
            'a': ({
                'name': u'NSB Department of Law',
                'address1': u'Pob 69',
                'city': u'Barrow',
                'state': u'AK',
                'zip_code': u'',
                'lookup_key': u'pob69barrownsbdepartmentoflawak',
            }, {
                'phone': u'',
                'fax': u'',
                'email': u'',
            })
        }, {
            # Unknown/invalid state.
            'q': """Kessler Topaz Meltzer Check LLP
                    280 King of Prussia Road
                    Radnor, OA 19087
                    (610) 667-7706
                    Fax: (610) 667-7056
                    Email: jneumann@ktmc.com
                """,
            'a': ({
                'name': u'Kessler Topaz Meltzer Check LLP',
                'city': u'Radnor',
                'address1': u'280 King of Prussia Road',
                'lookup_key': u'280kingofprussiaroadradnorkesslertopazmeltzercheck19087',
                'state': u'',
                'zip_code': u'19087'
            }, {
                'phone': u'(610) 667-7706',
                'fax': u'(610) 667-7056',
                'email': u'jneumann@ktmc.com'
            })
        }]
        for i, pair in enumerate(pairs):
            print("Normalizing address %s..." % i, end='')
            result = normalize_attorney_contact(pair['q'])
            self.maxDiff = None
            self.assertEqual(result, pair['a'])
            print('✓')

    def test_making_a_lookup_key(self):
        self.assertEqual(
            make_address_lookup_key({
                'address1': u'400 Poydras St.',
                'address2': u'Suite 1200',
                'city': u'New Orleans',
                'name': u'Duncan and Sevin, LLC',
                'state': u'LA',
                'zip_code': u'70130',
            }),
            '400poydrasstsuite1200neworleansduncansevinllcla70130',
        )
        self.assertEqual(
            make_address_lookup_key({
                'name': 'Offices of Lissner AND Strook & Levin, LLP',
            }),
            'officeoflissnerstrooklevin',
        )


class TestFilesizeConversions(TestCase):

    def test_filesize_conversions(self):
        """Can we convert human filesizes to bytes?"""
        qa_pairs = [
            ('58 kb', 59392),
            ('117 kb', 119808),
            ('117kb', 119808),
            ('1 byte', 1),
            ('117 bytes', 117),
            ('117  bytes', 117),
            ('  117 bytes  ', 117),
            ('117b', 117),
            ('117bytes', 117),
            ('1 kilobyte', 1024),
            ('117 kilobytes', 119808),
            ('0.7 mb', 734003),
            ('1mb', 1048576),
            ('5.2 mb', 5452595),
        ]
        for qa in qa_pairs:
            print("Converting '%s' to bytes..." % qa[0], end='')
            self.assertEqual(convert_size_to_bytes(qa[0]), qa[1])
            print('✓')

