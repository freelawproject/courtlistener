from datetime import date

from reporters_db import REPORTERS
from cl.citations.find_citations import get_citations, is_date_in_reporter
from cl.citations import find_citations
from cl.citations.reporter_tokenizer import tokenize
from cl.citations.tasks import update_document
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.search.models import Opinion, OpinionsCited, OpinionCluster
from django.test import TestCase



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
             find_citations.Citation(volume=1, reporter='U.S.', page=1,
                                     canonical_reporter='U.S.', lookup_index=0,
                                     court='scotus')),
            # Basic test of non-case name before citation (should not be found)
            ('lissner test 1 U.S. 1',
             find_citations.Citation(volume=1, reporter='U.S.', page=1,
                                     canonical_reporter='U.S.', lookup_index=0,
                                     court='scotus')),
            # Test with plaintiff and defendant
            ('lissner v. test 1 U.S. 1',
             find_citations.Citation(plaintiff='lissner', defendant='test',
                                     volume=1, reporter='U.S.', page=1,
                                     canonical_reporter='U.S.', lookup_index=0,
                                     court='scotus')),
            # Test with plaintiff, defendant and year
            ('lissner v. test 1 U.S. 1 (1982)',
             find_citations.Citation(plaintiff='lissner', defendant='test',
                                     volume=1, reporter='U.S.', page=1,
                                     year=1982, canonical_reporter='U.S.',
                                     lookup_index=0, court='scotus')),
            # Test with different reporter than all of above.
            ('bob lissner v. test 1 F.2d 1 (1982)',
             find_citations.Citation(plaintiff='lissner', defendant='test',
                                     volume=1, reporter='F.2d', page=1,
                                     year=1982,
                                     canonical_reporter='F.', lookup_index=0)),
            # Test with court and extra information
            ('bob lissner v. test 1 U.S. 12, 347-348 (4th Cir. 1982)',
             find_citations.Citation(plaintiff='lissner', defendant='test',
                                     volume=1, reporter='U.S.', page=12,
                                     year=1982, extra=u'347-348', court='ca4',
                                     canonical_reporter='U.S.',
                                     lookup_index=0)),
            # Test with text before and after and a variant reporter
            ('asfd 22 U. S. 332 (1975) asdf',
             find_citations.Citation(volume=22, reporter='U.S.', page=332,
                                     year=1975, canonical_reporter='U.S.',
                                     lookup_index=0,
                                     court='scotus')),
            # Test with finding reporter when it's a second edition
            ('asdf 22 A.2d 332 asdf',
             find_citations.Citation(volume=22, reporter='A.2d', page=332,
                                     canonical_reporter='A.', lookup_index=0)),
            # Test finding a variant second edition reporter
            ('asdf 22 A. 2d 332 asdf',
             find_citations.Citation(volume=22, reporter='A.2d', page=332,
                                     canonical_reporter='A.', lookup_index=0)),
            # Test finding a variant of an edition resolvable by variant alone.
            ('171 Wn.2d 1016',
             find_citations.Citation(volume=171, reporter='Wash. 2d',
                                     page=1016, canonical_reporter='Wash.',
                                     lookup_index=1)),
        )
        for q, a in test_pairs:
            cite_found = get_citations(q)[0]
            self.assertEqual(
                cite_found,
                a,
                msg='%s\n%s != \n%s' % (
                    q,
                    cite_found.__dict__,
                    a.__dict__
                )
            )

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
             [find_citations.Citation(volume=1, reporter='P.R.R.', page=1,
                                      canonical_reporter='P.R.R.',
                                      lookup_index=0)]),
            # 2. U. S. --> A simple variant to resolve.
            ('1 U. S. 1',
             [find_citations.Citation(volume=1, reporter='U.S.', page=1,
                                      canonical_reporter='U.S.',
                                      lookup_index=0,
                                      court='scotus')]),
            # 3. A.2d --> Not a variant, but needs to be looked up in the
            #    EDITIONS variable.
            ('1 A.2d 1',
             [find_citations.Citation(volume=1, reporter='A.2d', page=1,
                                      canonical_reporter='A.',
                                      lookup_index=0)]),
            # 4. A. 2d --> An unambiguous variant of an edition
            ('1 A. 2d 1',
             [find_citations.Citation(volume=1, reporter='A.2d', page=1,
                                      canonical_reporter='A.',
                                      lookup_index=0)]),
            # 5. P.R. --> A variant of 'Pen. & W.', 'P.R.R.', or 'P.' that's
            #    resolvable by year
            ('1 P.R. 1 (1831)',
             # Of the three, only Pen & W. was being published this year.
             [find_citations.Citation(volume=1, reporter='Pen. & W.', page=1,
                                      canonical_reporter='Pen. & W.',
                                      lookup_index=0, year=1831)]),
            # 5.1: W.2d --> A variant of an edition that either resolves to
            #      'Wis. 2d' or 'Wash. 2d' and is resolvable by year.
            ('1 W.2d 1 (1854)',
             # Of the two, only Wis. 2d was being published this year.
             [find_citations.Citation(volume=1, reporter='Wis. 2d', page=1,
                                      canonical_reporter='Wis.',
                                      lookup_index=0,
                                      year=1854)]),
            # 5.2: Wash. --> A non-variant that has more than one reporter for
            #      the key, but is resolvable by year
            ('1 Wash. 1 (1890)',
             [find_citations.Citation(volume=1, reporter='Wash.', page=1,
                                      canonical_reporter='Wash.',
                                      lookup_index=1,
                                      year=1890)]),
            # 6. Cr. --> A variant of Cranch, which is ambiguous, except with
            #    paired with this variation.
            ('1 Cr. 1',
             [find_citations.Citation(volume=1, reporter='Cranch', page=1,
                                      canonical_reporter='Cranch',
                                      lookup_index=0,
                                      court='scotus')]),
            # 7. Cranch. --> Not a variant, but could refer to either Cranch's
            #    Supreme Court cases or his DC ones. In this case, we cannot
            #    disambiguate. Years are not known, and we have no further
            #    clues. We must simply drop Cranch from the results.
            ('1 Cranch 1 1 U.S. 23',
             [find_citations.Citation(volume=1, reporter='U.S.', page=23,
                                      canonical_reporter='U.S.',
                                      lookup_index=0,
                                      court='scotus')]),
            # 8. Unsolved problem. In theory, we could use parallel citations
            #    to resolve this, because Rob is getting cited next to La., but
            #    we don't currently know the proximity of citations to each
            #    other, so can't use this.
            #  - Rob. --> Either:
            #                8.1: A variant of Robards (1862-1865) or
            #                8.2: Robinson's Louisiana Reports (1841-1846) or
            #                8.3: Robinson's Virgina Reports (1842-1865)
            #('1 Rob. 1 1 La. 1',
            # [find_citations.Citation(volume=1, reporter='Rob.', page=1,
            #                          canonical_reporter='Rob.',
            #                          lookup_index=0),
            #  find_citations.Citation(volume=1, reporter='La.', page=1,
            #                          canonical_reporter='La.',
            #                          lookup_index=0)]),
        ]
        for pair in test_pairs:
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


class MatchingTest(IndexedSolrTestCase):

    def test_citation_matching(self):
        """Creates a few documents that contain specific citations, then
        attempts to find and match those citations.

        This becomes a bit of an integration test, which is fine.
        """
        # Delete all the connections between items that are in the fixtures by
        # default, and reset counts to zero.
        OpinionsCited.objects.all().delete()
        OpinionCluster.objects.all().update(citation_count=0)

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

    def test_basic_cited_by_feed(self):
        """Can we load the cited-by feed without it crashing?"""
        # TODO: Use example from audio.tests to upgrade this to check for
        # actual content. This is weak sauce just to test for non-crashingness.
        r = self.client.get('/feed/2/cited-by/')
        self.assertEqual(r.status_code, 200)

    def test_unicode_content(self):
        """Does the citation feed continue working even when we have a unicode
        case name?
        """
        cite = Document.objects.get(pk=1).citation
        orig_case_name = cite.case_name
        new_case_name = u'MAC ARTHUR KAMMUELLER, \u2014 v. LOOMIS, FARGO & ' \
                        u'CO., \u2014'
        cite.case_name = new_case_name
        cite.save()

        r = self.client.get('/feed/1/cited-by/')
        self.assertEqual(r.status_code, 200)

        cite.case_name = orig_case_name
        cite.save()
