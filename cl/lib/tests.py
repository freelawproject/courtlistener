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
from cl.lib.pacer import normalize_party_types, normalize_attorney_role
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
            'mp3/2015/1/1/something_v._something_else.mp3':'audio/mpeg',
            'doc/2015/1/1/voutila_v._bonvini.doc':'application/msword',
            'pdf/2015/1/1/voutila_v._bonvini.pdf':'application/pdf',
            'txt/2015/1/1/voutila_v._bonvini.txt':'text/plain',
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
            'a': Role.INACTIVE,
        }, {
            'q': 'ATTORNEY IN SEALED GROUP',
            'a': Role.ATTORNEY_IN_SEALED_GROUP,
        }, {
            'q': 'ATTORNEY TO BE NOTICED',
            'a': Role.ATTORNEY_TO_BE_NOTICED,
        }, {
            'q': 'Bar Status: ACTIVE',
            'a': None,
        }, {
            'q': 'DISBARRED 02/19/2010',
            'a': Role.DISBARRED,
        }, {
            'q': 'Designation: ADR Pro Bono Limited Scope Counsel',
            'a': None,
        }, {
            'q': 'LEAD ATTORNEY',
            'a': Role.ATTORNEY_LEAD,
        }, {
            'q': 'PRO HAC VICE',
            'a': Role.PRO_HAC_VICE,
        }, {
            'q': 'SELF- TERMINATED: 01/14/2013',
            'a': Role.SELF_TERMINATED,
        }, {
            'q': 'SUSPENDED 01/22/2016',
            'a': Role.SUSPENDED,
        }, {
            'q': 'TERMINATED: 01/01/2007',
            'a': Role.TERMINATED,
        }]
        for pair in pairs:
            print "Normalizing PACER role of '%s' to '%s'..." % \
                  (pair['q'], pair['a']),
            result = normalize_attorney_role(pair['q'])
            self.assertEqual(result, pair['a'])
            print '✓'
        with self.assertRaises(ValueError):
            normalize_attorney_role('this is an unknown role')
