# coding=utf-8
from django.core.urlresolvers import reverse
from reporters_db import REPORTERS
from cl.citations.find_citations import get_citations, is_date_in_reporter, \
    Citation
from cl.citations.management.commands.cl_add_parallel_citations import \
    identify_parallel_citations, make_edge_list, monkey_patch_citations
from cl.citations.reporter_tokenizer import tokenize
from cl.citations.tasks import update_document, create_cited_html
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.search.models import Opinion, OpinionsCited, OpinionCluster

from datetime import date
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase
from lxml import etree


def remove_citations_from_imported_fixtures():
    """Delete all the connections between items that are in the fixtures by
    default, and reset counts to zero.
    """
    OpinionsCited.objects.all().delete()
    OpinionCluster.objects.all().update(citation_count=0)


class CiteTest(TestCase):
    fixtures = ['court_data.json']

    def test_reporter_tokenizer(self):
        """Do we tokenize correctly?"""
        self.assertEqual(tokenize('See Roe v. Wade, 410 U. S. 113 (1973)'),
                         ['See', 'Roe', 'v.', 'Wade,', '410', 'U. S.', '113',
                          '(1973)'])
        self.assertEqual(tokenize('Foo bar eats grue, 232 Vet. App. (2003)'),
                         ['Foo', 'bar', 'eats', 'grue,', '232', 'Vet. App.',
                          '(2003)'])

    def test_find_citations(self):
        """Can we find and make Citation objects from strings?"""
        test_pairs = (
            # Basic test
            ('1 U.S. 1',
             [Citation(volume=1, reporter='U.S.', page=1,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=1,
                       reporter_found='U.S.')]),
            # Basic test of non-case name before citation (should not be found)
            ('lissner test 1 U.S. 1',
             [Citation(volume=1, reporter='U.S.', page=1,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=3,
                       reporter_found='U.S.')]),
            # Test with plaintiff and defendant
            ('lissner v. test 1 U.S. 1',
             [Citation(plaintiff='lissner', defendant='test', volume=1,
                       reporter='U.S.', page=1, canonical_reporter=u'U.S.',
                       lookup_index=0, court='scotus', reporter_index=4,
                       reporter_found='U.S.')]),
            # Test with plaintiff, defendant and year
            ('lissner v. test 1 U.S. 1 (1982)',
             [Citation(plaintiff='lissner', defendant='test', volume=1,
                       reporter='U.S.', page=1, year=1982,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=4,
                       reporter_found='U.S.')]),
            # Test with different reporter than all of above.
            ('bob lissner v. test 1 F.2d 1 (1982)',
             [Citation(plaintiff='lissner', defendant='test', volume=1,
                       reporter='F.2d', page=1, year=1982,
                       canonical_reporter=u'F.', lookup_index=0,
                       reporter_index=5, reporter_found='F.2d')]),
            # Test with court and extra information
            ('bob lissner v. test 1 U.S. 12, 347-348 (4th Cir. 1982)',
             [Citation(plaintiff='lissner', defendant='test', volume=1,
                       reporter='U.S.', page=12, year=1982, extra=u'347-348',
                       court='ca4', canonical_reporter=u'U.S.', lookup_index=0,
                       reporter_index=5, reporter_found='U.S.')]),
            # Test with text before and after and a variant reporter
            ('asfd 22 U. S. 332 (1975) asdf',
             [Citation(volume=22, reporter='U.S.', page=332, year=1975,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=2,
                       reporter_found='U. S.')]),
            # Test with finding reporter when it's a second edition
            ('asdf 22 A.2d 332 asdf',
             [Citation(volume=22, reporter='A.2d', page=332,
                       canonical_reporter=u'A.', lookup_index=0,
                       reporter_index=2, reporter_found='A.2d')]),
            # Test finding a variant second edition reporter
            ('asdf 22 A. 2d 332 asdf',
             [Citation(volume=22, reporter='A.2d', page=332,
                       canonical_reporter=u'A.', lookup_index=0,
                       reporter_index=2, reporter_found='A. 2d')]),
            # Test finding a variant of an edition resolvable by variant alone.
            ('171 Wn.2d 1016',
             [Citation(volume=171, reporter='Wash. 2d', page=1016,
                       canonical_reporter=u'Wash.', lookup_index=1,
                       reporter_index=1, reporter_found='Wn.2d')]),
            # Test finding two citations where one of them has abutting
            # punctuation.
            ('2 U.S. 3, 4-5 (3 Atl. 33)',
             [Citation(volume=2, reporter="U.S.", page=3, extra=u'4-5',
                       canonical_reporter=u"U.S.", lookup_index=0,
                       reporter_index=1, reporter_found="U.S.", court='scotus'),
              Citation(volume=3, reporter="A.", page=33,
                       canonical_reporter=u"A.", lookup_index=0,
                       reporter_index=5, reporter_found="Atl.")]),
        )
        for q, a in test_pairs:
            print "Testing citation extraction for %s..." % q,
            cites_found = get_citations(q)
            self.assertEqual(
                cites_found,
                a,
                msg='%s\n%s\n\n    !=\n\n%s' % (
                    q,
                    ",\n".join([str(cite.__dict__) for cite in cites_found]),
                    ",\n".join([str(cite.__dict__) for cite in a]),
                )
            )
            print "✓"

    def test_date_in_editions(self):
        test_pairs = [
            ('S.E.', 1886, False),
            ('S.E.', 1887, True),
            ('S.E.', 1939, True),
            ('S.E.', 2012, True),
            ('T.C.M.', 1950, True),
            ('T.C.M.', 1940, False),
            ('T.C.M.', date.today().year + 1, False),
        ]
        for pair in test_pairs:
            date_in_reporter = is_date_in_reporter(
                    REPORTERS[pair[0]][0]['editions'], pair[1])
            self.assertEqual(
                    date_in_reporter, pair[2],
                    msg='is_date_in_reporter(REPORTERS[%s][0]["editions"], %s) != '
                        '%s\nIt\'s equal to: %s' %
                        (pair[0], pair[1], pair[2], date_in_reporter))

    def test_disambiguate_citations(self):
        test_pairs = [
            # 1. P.R.R --> Correct abbreviation for a reporter.
            ('1 P.R.R. 1',
             [Citation(volume=1, reporter='P.R.R.', page=1,
                       canonical_reporter=u'P.R.R.', lookup_index=0,
                       reporter_index=1, reporter_found='P.R.R.')]),
            # 2. U. S. --> A simple variant to resolve.
            ('1 U. S. 1',
             [Citation(volume=1, reporter='U.S.', page=1,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=1,
                       reporter_found='U. S.')]),
            # 3. A.2d --> Not a variant, but needs to be looked up in the
            #    EDITIONS variable.
            ('1 A.2d 1',
             [Citation(volume=1, reporter='A.2d', page=1,
                       canonical_reporter=u'A.', lookup_index=0,
                       reporter_index=1, reporter_found='A.2d')]),
            # 4. A. 2d --> An unambiguous variant of an edition
            ('1 A. 2d 1',
             [Citation(volume=1, reporter='A.2d', page=1,
                       canonical_reporter=u'A.', lookup_index=0,
                       reporter_index=1, reporter_found='A. 2d')]),
            # 5. P.R. --> A variant of 'Pen. & W.', 'P.R.R.', or 'P.' that's
            #    resolvable by year
            ('1 P.R. 1 (1831)',
             # Of the three, only Pen & W. was being published this year.
             [Citation(volume=1, reporter='Pen. & W.', page=1,
                       canonical_reporter=u'Pen. & W.', lookup_index=0,
                       year=1831, reporter_index=1, reporter_found='P.R.')]),
            # 5.1: W.2d --> A variant of an edition that either resolves to
            #      'Wis. 2d' or 'Wash. 2d' and is resolvable by year.
            ('1 W.2d 1 (1854)',
             # Of the two, only Wis. 2d was being published this year.
             [Citation(volume=1, reporter='Wis. 2d', page=1,
                       canonical_reporter=u'Wis.', lookup_index=0,
                       year=1854, reporter_index=1, reporter_found='W.2d')]),
            # 5.2: Wash. --> A non-variant that has more than one reporter for
            #      the key, but is resolvable by year
            ('1 Wash. 1 (1890)',
             [Citation(volume=1, reporter='Wash.', page=1,
                       canonical_reporter=u'Wash.', lookup_index=1, year=1890,
                       reporter_index=1, reporter_found='Wash.')]),
            # 6. Cr. --> A variant of Cranch, which is ambiguous, except with
            #    paired with this variation.
            ('1 Cr. 1',
             [Citation(volume=1, reporter='Cranch', page=1,
                       canonical_reporter=u'Cranch', lookup_index=0,
                       court='scotus', reporter_index=1,
                       reporter_found='Cr.')]),
            # 7. Cranch. --> Not a variant, but could refer to either Cranch's
            #    Supreme Court cases or his DC ones. In this case, we cannot
            #    disambiguate. Years are not known, and we have no further
            #    clues. We must simply drop Cranch from the results.
            ('1 Cranch 1 1 U.S. 23',
             [Citation(volume=1, reporter='U.S.', page=23,
                       canonical_reporter=u'U.S.', lookup_index=0,
                       court='scotus', reporter_index=4,
                       reporter_found='U.S.')]),
            # 8. Unsolved problem. In theory, we could use parallel citations
            #    to resolve this, because Rob is getting cited next to La., but
            #    we don't currently know the proximity of citations to each
            #    other, so can't use this.
            #  - Rob. --> Either:
            #                8.1: A variant of Robards (1862-1865) or
            #                8.2: Robinson's Louisiana Reports (1841-1846) or
            #                8.3: Robinson's Virgina Reports (1842-1865)
            # ('1 Rob. 1 1 La. 1',
            # [Citation(volume=1, reporter='Rob.', page=1,
            #                          canonical_reporter='Rob.',
            #                          lookup_index=0),
            #  Citation(volume=1, reporter='La.', page=1,
            #                          canonical_reporter='La.',
            #                          lookup_index=0)]),
        ]
        for pair in test_pairs:
            print "Testing disambiguation for %s..." % pair[0],
            citations = get_citations(pair[0], html=False)
            self.assertEqual(
                citations, pair[1],
                msg='%s\n%s != \n%s' %
                    (
                        pair[0],
                        [cite.__dict__ for cite in citations],
                        [cite.__dict__ for cite in pair[1]]
                    )
            )
            print "✓"

    def test_make_html(self):
        """Can we make basic HTML conversions properly?"""
        good_html = ('<pre class="inline">asdf </pre><span class="citation '
                     'no-link"><span class="volume">22</span> <span '
                     'class="reporter">U.S.</span> <span class="page">33</span>'
                     '</span><pre class="inline"> asdf</pre>')

        # Simple example
        s = 'asdf 22 U.S. 33 asdf'
        opinion = Opinion(plain_text=s)
        citations = get_citations(s)
        new_html = create_cited_html(opinion, citations)
        self.assertEqual(
            good_html,
            new_html,
        )

        # Using a variant format for U.S. (Issue #409)
        s = 'asdf 22 U. S. 33 asdf'
        opinion = Opinion(plain_text=s)
        citations = get_citations(s)
        new_html = create_cited_html(opinion, citations)
        self.assertEqual(
            good_html,
            new_html,
        )


class MatchingTest(IndexedSolrTestCase):
    def test_citation_matching(self):
        """Creates a few documents that contain specific citations, then
        attempts to find and match those citations.

        This becomes a bit of an integration test, which is fine.
        """
        remove_citations_from_imported_fixtures()

        citing = Opinion.objects.get(pk=3)
        update_document(citing)  # Updates d1's citation count in a Celery task

        cited = Opinion.objects.get(pk=2)
        expected_count = 1
        self.assertEqual(
            cited.cluster.citation_count,
            expected_count,
            msg=u"'cited' was not updated by a citation found in 'citing', or "
                u"the citation was not found. Count was: %s instead of %s"
                % (cited.cluster.citation_count, expected_count)
        )


class CitationFeedTest(TestCase):
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json']

    def _tree_has_content(self, content, expected_count):
        xml_tree = etree.fromstring(content)
        count = len(xml_tree.xpath(
            '//a:entry',
            namespaces={'a': 'http://www.w3.org/2005/Atom'})
        )
        self.assertEqual(
            count,
            expected_count,
        )

    def test_basic_cited_by_feed(self):
        """Can we load the cited-by feed and does it have content?"""
        r = self.client.get(
            reverse('search_feed', args=['search']),
            {'q': 'cites:1'}
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)

    def test_unicode_content(self):
        """Does the citation feed continue working even when we have a unicode
        case name?
        """
        new_case_name = u'MAC ARTHUR KAMMUELLER, \u2014 v. LOOMIS, FARGO & ' \
                        u'CO., \u2014'
        OpinionCluster.objects.filter(pk=1).update(case_name=new_case_name)

        r = self.client.get('/feed/search/?q=cites:1')
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)


class CitationCommandTest(IndexedSolrTestCase):
    """Test a variety of the ways that cl_find_citations can be called."""

    def call_command_and_test_it(self, args):
        remove_citations_from_imported_fixtures()
        call_command('cl_find_citations', *args)
        cited = Opinion.objects.get(pk=2)
        expected_count = 1
        self.assertEqual(
            cited.cluster.citation_count,
            expected_count,
            msg=u"'cited' was not updated by a citation found in 'citing', or "
                u"the citation was not found. Count was: %s instead of %s"
                % (cited.cluster.citation_count, expected_count)
        )

    def test_index_by_doc_id(self):
        args = [
            '--doc_id', '3',
            '--index', 'concurrently',
        ]
        self.call_command_and_test_it(args)

    def test_index_by_doc_ids(self):
        args = [
            '--doc_id', '3', '2',
            '--index', 'concurrently',
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_only(self):
        args = [
            '--start_id', '0',
            '--index', 'concurrently',
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_and_end(self):
        args = [
            '--start_id', '0',
            '--end_id', '5',
            '--index', 'concurrently',
        ]
        self.call_command_and_test_it(args)

    def test_filed_after(self):
        args = [
            '--filed_after', '2015-06-09',
            '--index', 'concurrently',
        ]
        self.call_command_and_test_it(args)


class ParallelCitationTest(SimpleTestCase):
    def test_identifying_parallel_citations(self):
        """Given a string, can we identify parallel citations"""
        tests = (
            # A pair consisting of a test string and the number of parallel
            # citations that should be identifiable in that string.
            # Simple case
            ("1 U.S. 1 (22 U.S. 33)", 1, 2),
            # Too far apart
            ("1 U.S. 1 too many words 22 U.S. 33", 0, 0),
            # Three citations
            ("1 U.S. 1, (44 U.S. 33, 99 U.S. 100)", 1, 3),
            # Parallel citation after a valid citation too early on
            ("1 U.S. 1 too many words, then 22 U.S. 33, 13 WL 33223", 1, 2),
        )
        for q, citation_group_count, expected_num_parallel_citations in tests:
            print "Testing parallel citation identification for: %s..." % q,
            citations = get_citations(q)
            citation_groups = identify_parallel_citations(citations)
            computed_num_citation_groups = len(citation_groups)
            self.assertEqual(
                computed_num_citation_groups,
                citation_group_count,
                msg="Did not have correct number of citation groups. Got %s, "
                    "not %s." % (computed_num_citation_groups,
                                 citation_group_count)
            )
            if not citation_groups:
                # Add an empty list to make testing easier.
                citation_groups = [[]]
            computed_num_parallel_citation = len(citation_groups[0])
            self.assertEqual(
                computed_num_parallel_citation,
                expected_num_parallel_citations,
                msg="Did not identify correct number of parallel citations in "
                    "the group. Got %s, not %s" % (
                        computed_num_parallel_citation,
                        expected_num_parallel_citations,
                    )
            )
            print '✓'

    def test_making_edge_list(self):
        """Can we make networkx-friendly edge lists?"""
        tests = [
            ([1, 2], [(1, 2)]),
            ([1, 2, 3], [(1, 2), (2, 3)]),
            ([1, 2, 3, 4], [(1, 2), (2, 3), (3, 4)]),
        ]
        for q, a in tests:
            self.assertEqual(
                make_edge_list(q),
                a,
            )

    def test_monkey_patching(self):
        """Can we make the regular equality operator do near duping?"""
        citations = [
            Citation(reporter=2, volume="U.S.", page="2", reporter_index=1),
            Citation(reporter=2, volume="U.S.", page="2", reporter_index=2),
        ]
        # Before monkey patching, they differ
        self.assertNotEqual(
            citations[0],
            citations[1],
        )

        # After patching, they're the same!
        monkey_patch_citations()
        self.assertEqual(
            citations[0],
            citations[1],
        )
