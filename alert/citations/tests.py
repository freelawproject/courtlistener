from alert.citations.constants import REPORTERS
from alert.citations.find_citations import get_citations, Citation, disambiguate_reporters, is_date_in_reporter
from alert.citations.reporter_tokenizer import tokenize
from django.test import TestCase

from datetime import date


class CiteTest(TestCase):
    def test_reporter_tokenizer(self):
        """Do we tokenize correctly?"""
        self.assertEqual(tokenize('See Roe v. Wade, 410 U. S. 113 (1973)'),
                         ['See', 'Roe', 'v.', 'Wade,', '410', 'U. S.', '113', '(1973)'])
        self.assertEqual(tokenize('Foo bar eats grue, 232 Vet. App. (2003)'),
                         ['Foo', 'bar', 'eats', 'grue,', '232', 'Vet. App.', '(2003)'])

    def test_find_citations(self):
        """Can we find and make Citation objects from strings?"""
        test_pairs = (
            # Basic test
            ('1 U.S. 1',
             Citation(volume=1, reporter='U.S.', page=1, canonical_reporter='U.S.', lookup_index=0)),
            # Basic test of non-case name before citation (should not be found)
            ('lissner test 1 U.S. 1',
             Citation(volume=1, reporter='U.S.', page=1, canonical_reporter='U.S.', lookup_index=0)),
            # Test with plaintiff and defendant
            ('lissner v. test 1 U.S. 1',
             Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1,
                      canonical_reporter='U.S.', lookup_index=0)),
            # Test with plaintiff, defendant and year
            ('lissner v. test 1 U.S. 1 (1982)',
             Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1, year=1982,
                      canonical_reporter='U.S.', lookup_index=0)),
            # Test with different reporter than all of above.
            ('bob lissner v. test 1 F.2d 1 (1982)',
             Citation(plaintiff='lissner', defendant='test', volume=1, reporter='F.2d', page=1, year=1982,
                      canonical_reporter='F.', lookup_index=0)),
            # Test with court and extra information
            ('bob lissner v. test 1 U.S. 1, 347-348 (4th Cir. 1982)',
             Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1, year=1982,
                      extra='347-348', court='4th Cir', canonical_reporter='U.S.', lookup_index=0)),
            # Test with text before and after and a variant reporter
            ('asfd 22 U. S. 332 (1975) asdf',
             Citation(volume=22, reporter='U.S.', page=332, year=1975, canonical_reporter='U.S.', lookup_index=0)),
            # Test with finding reporter when it's a second edition
            ('asdf 22 A.2d 332 asdf',
             Citation(volume=22, reporter='A.2d', page=332, canonical_reporter='A.', lookup_index=0)),
            # Test finding a variant second edition reporter
            ('asdf 22 A. 2d 332 asdf',
             Citation(volume=22, reporter='A.2d', page=332, canonical_reporter='A.', lookup_index=0)),
            # Test finding a variant of an edition resolvable by variant alone.
            ('171 Wn.2d 1016',
             Citation(volume=171, reporter='Wash. 2d', page=1016, canonical_reporter='Wash.', lookup_index=1)),
            ('171 Wn.2d 1016 (1982)',
             Citation(volume=171, reporter='Wash. 2d', page=1016, canonical_reporter='Wash.', lookup_index=1, year=1982)),
        )
        for pair in test_pairs:
            cite_found = get_citations(pair[0])[0]
            self.assertEqual(cite_found, pair[1],
                             msg='%s\n%s != \n%s' % (pair[0], cite_found.__dict__, pair[1].__dict__))

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
            date_in_reporter = is_date_in_reporter(REPORTERS[pair[0]][0]['editions'], pair[1])
            self.assertEqual(date_in_reporter, pair[2],
                             msg='is_date_in_reporter(REPORTERS[%s][0]["editions"], %s) != %s\nIt\'s equal to: %s' %
                                 (pair[0], pair[1], pair[2], date_in_reporter))

    def test_disambiguate_citations(self):
        test_pairs = [
            # 1. P.R.R --> Correct abbreviation for a reporter.
            ('1 P.R.R. 1',
             [Citation(volume=1, reporter='P.R.R.', page=1, canonical_reporter='P.R.R.', lookup_index=0)]),
            # 2. U. S. --> A simple variant to resolve.
            ('1 U. S. 1',
             [Citation(volume=1, reporter='U.S.', page=1, canonical_reporter='U.S.', lookup_index=0)]),
            # 3. A.2d --> Not a variant, but needs to be looked up in the EDITIONS variable.
            ('1 A.2d 1',
             [Citation(volume=1, reporter='A.2d', page=1, canonical_reporter='A.', lookup_index=0)]),
            # 4. A. 2d --> An unambiguous variant of an edition
            ('1 A. 2d 1',
             [Citation(volume=1, reporter='A.2d', page=1, canonical_reporter='A.', lookup_index=0)]),
            # 5. P.R. --> A variant of 'Pen. & W.', 'P.R.R.', or 'P.' that's resolvable by year
            ('1 P.R. 1 (1831)',  # Of the three, only Pen & W. was being published this year.
             [Citation(volume=1, reporter='Pen. & W.', page=1, canonical_reporter='Pen. & W.', lookup_index=0, year=1831)]),
            # 5.1: W.2d --> A variant of an edition that either resolves to 'Wis. 2d' or 'Wash. 2d' and is resolvable
            #               by year.
            ('1 W.2d 1 (1854)',  # Of the two, only Wis. 2d was being published this year.
             [Citation(volume=1, reporter='Wis. 2d', page=1, canonical_reporter='Wis.', lookup_index=0, year=1854)]),
            # 5.2: Wash. --> A non-variant that has more than one reporter for the key, but is resolvable by year
            ('1 Wash. 1 (1890)',
             [Citation(volume=1, reporter='Wash.', page=1, canonical_reporter='Wash.', lookup_index=1, year=1890)]),
            # 6. Cr. --> A variant of Cranch, which is ambiguous, except with paired with this variation.
            ('1 Cr. 1',
             [Citation(volume=1, reporter='Cranch', page=1, canonical_reporter='Cranch', lookup_index=0)]),
            # 7. Cranch. --> Not a variant, but could refer to either Cranch's Supreme Court cases or his DC ones.
            #                In this case, we disambiguate based on parallel citations because years won't provide
            #                enough information.
            #('1 Cranch. 1 1 U.S. 23',
            # [Citation(volume=1, reporter='Cranch', page=1, canonical_reporter='Cranch', lookup_index=0),
            #  Citation(volume=1, reporter='U.S.', page=1, canonical_reporter='U.S.', lookup_index=0)]),
            # 8. Rob. --> Either:
            #                8.1: A variant of Robards (1862-1865) or
            #                8.2: Robinson's Louisiana Reports (1841-1846) or
            #                8.3: Robinson's Virgina Reports (1842-1865)
            #('1 Rob. 1 1 La. 1',
            # [Citation(volume=1, reporter='Rob.', page=1, canonical_reporter='Rob.', lookup_index=0),
            #  Citation(volume=1, reporter='La.', page=1, canonical_reporter='La.', lookup_index=0)]),
        ]
        for pair in test_pairs:
            citations = get_citations(pair[0], html=False)
            self.assertEqual(citations, pair[1],
                             msg='%s\n%s != \n%s' % (pair[0], [cite.__dict__ for cite in citations],
                                                     [cite.__dict__ for cite in pair[1]]))

