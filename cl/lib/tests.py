# coding=utf8
"""
Unit tests for lib
"""
import datetime
from django.test import TestCase
from cl.lib.string_utils import trunc
from cl.lib.search_utils import make_fq
from cl.lib.model_helpers import make_upload_path
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
