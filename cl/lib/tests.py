# coding=utf8
"""
Unit tests for lib
"""
import datetime

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test import override_settings
from rest_framework.status import HTTP_503_SERVICE_UNAVAILABLE, HTTP_200_OK

from cl.lib.mime_types import lookup_mime_type
from cl.lib.model_helpers import make_upload_path
from cl.lib.pacer import normalize_party_types, normalize_attorney_role, \
    normalize_attorney_contact, normalize_us_state, make_lookup_key
from cl.lib.search_utils import make_fq
from cl.lib.string_utils import trunc
from cl.people_db.models import Role
from cl.search.models import Opinion, OpinionCluster, Docket, Court


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
        self.client.login(username='admin', password='password')
        r = self.client.get(reverse('show_results'))
        self.assertEqual(
            r.status_code,
            HTTP_200_OK,
            'Staff did not get through, but should have. Staff got status code '
            'of: %s instead of %s' % (r.status_code, HTTP_200_OK)
        )


class TestPACERPartyParsing(TestCase):
    """Various tests for the PACER party parsers."""

    def test_party_type_normalization(self):
        pairs = [{
            'q': 'Defendant                                 (1)',
            'a': 'Defendant'
        }, {
            'q': 'Debtor 2',
            'a': 'Debtor',
        }, {
            'q': 'ThirdParty Defendant',
            'a': 'Third Party Defendant',
        }, {
            'q': 'ThirdParty Plaintiff',
            'a': 'Third Party Plaintiff',
        }, {
            'q': '3rd Pty Defendant',
            'a': 'Third Party Defendant',
        }, {
            'q': '3rd party defendant',
            'a': 'Third Party Defendant',
        }, {
            'q': 'Counter-defendant',
            'a': 'Counter Defendant',
        }, {
            'q': 'Counter-Claimaint',
            'a': 'Counter Claimaint',
        }, {
            'q': 'US Trustee',
            'a': 'U.S. Trustee',
        }, {
            'q': 'United States Trustee',
            'a': 'U.S. Trustee',
        }, {
            'q': 'U. S. Trustee',
            'a': 'U.S. Trustee',
        }, {
            'q': 'BUS BOY',
            'a': 'Bus Boy',
        }, {
            'q': 'JointAdmin Debtor',
            'a': 'Jointly Administered Debtor',
        }, {
            'q': 'Intervenor-Plaintiff',
            'a': 'Intervenor Plaintiff',
        }, {
            'q': 'Intervenor Dft',
            'a': 'Intervenor Defendant',
        }]
        for pair in pairs:
            print "Normalizing PACER type of '%s' to '%s'..." % \
                  (pair['q'], pair['a']),
            result = normalize_party_types(pair['q'])
            self.assertEqual(result, pair['a'])
            print '✓'

    def test_attorney_role_normalization(self):
        """Can we normalize the attorney roles into a small number of roles?"""
        pairs = [{
            'q': '(Inactive)',
            'a': {'role': Role.INACTIVE, 'date_action': None},
        }, {
            'q': 'ATTORNEY IN SEALED GROUP',
            'a': {'role': Role.ATTORNEY_IN_SEALED_GROUP, 'date_action': None},
        }, {
            'q': 'ATTORNEY TO BE NOTICED',
            'a': {'role': Role.ATTORNEY_TO_BE_NOTICED, 'date_action': None},
        }, {
            'q': 'Bar Status: ACTIVE',
            'a': {'role': None, 'date_action': None},
        }, {
            'q': 'DISBARRED 02/19/2010',
            'a': {'role': Role.DISBARRED,
                  'date_action': datetime.date(2010, 2, 19)},
        }, {
            'q': 'Designation: ADR Pro Bono Limited Scope Counsel',
            'a': {'role': None, 'date_action': None},
        }, {
            'q': 'LEAD ATTORNEY',
            'a': {'role': Role.ATTORNEY_LEAD, 'date_action': None},
        }, {
            'q': 'PRO HAC VICE',
            'a': {'role': Role.PRO_HAC_VICE, 'date_action': None},
        }, {
            'q': 'SELF- TERMINATED: 01/14/2013',
            'a': {'role': Role.SELF_TERMINATED,
                  'date_action': datetime.date(2013, 1, 14)},
        }, {
            'q': 'SUSPENDED 01/22/2016',
            'a': {'role': Role.SUSPENDED,
                  'date_action': datetime.date(2016, 1, 22)},
        }, {
            'q': 'TERMINATED: 01/01/2007',
            'a': {'role': Role.TERMINATED,
                  'date_action': datetime.date(2007, 1, 1)},
        }]
        for pair in pairs:
            print "Normalizing PACER role of '%s' to '%s'..." % \
                  (pair['q'], pair['a']),
            result = normalize_attorney_role(pair['q'])
            self.assertEqual(result, pair['a'])
            print '✓'
        with self.assertRaises(ValueError):
            normalize_attorney_role('this is an unknown role')

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
            print "Normalizing state of '%s' to '%s'..." % \
                  (pair['q'], pair['a']),
            result = normalize_us_state(pair['q'])
            self.assertEqual(result, pair['a'])
            print '✓'

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
                'phone': u'907-276-5152',
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
                'phone': u'804648-1636',
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
                'phone': u"804648-1636",
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
                'phone': u'206-373-7381',
                'fax': u'206-516-3883',
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
                'phone': u'614228-3727',
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
                'phone': '304342-3174',
                'fax': '304342-0448',
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
                'phone': u'303-861-1764',
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
                'fax': u'626-229-9615',
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
                'phone': u'504-585-3800',
                'email': u'darden@carverdarden.com',
                'fax': u'',
            })
        }]
        for i, pair in enumerate(pairs):
            print "Normalizing address %s..." % i,
            result = normalize_attorney_contact(pair['q'])
            self.maxDiff = None
            self.assertEqual(result, pair['a'])
            print '✓'

    def test_making_a_lookup_key(self):
        self.assertEqual(
            make_lookup_key({
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
            make_lookup_key({
                'name': 'Offices of Lissner AND Strook & Levin, LLP',
            }),
            'officeoflissnerstrooklevin',
        )
