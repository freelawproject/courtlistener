# coding=utf-8
from datetime import date

from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase, SimpleTestCase
from lxml import etree
from reporters_db import REPORTERS

from cl.citations.find_citations import get_citations, is_date_in_reporter
from cl.citations.models import (
    Citation,
    FullCitation,
    IdCitation,
    ShortformCitation,
    SupraCitation,
)
from cl.citations.management.commands.cl_add_parallel_citations import (
    identify_parallel_citations,
    make_edge_list,
)
from cl.citations.match_citations import match_citation, get_citation_matches
from cl.citations.reporter_tokenizer import tokenize
from cl.citations.tasks import (
    find_citations_for_opinion_by_pks,
    create_cited_html,
)
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.search.models import Opinion, OpinionsCited, OpinionCluster


def remove_citations_from_imported_fixtures():
    """Delete all the connections between items that are in the fixtures by
    default, and reset counts to zero.
    """
    OpinionsCited.objects.all().delete()
    OpinionCluster.objects.all().update(citation_count=0)


class CiteTest(TestCase):
    def test_reporter_tokenizer(self):
        """Do we tokenize correctly?"""
        self.assertEqual(
            tokenize("See Roe v. Wade, 410 U. S. 113 (1973)"),
            ["See", "Roe", "v.", "Wade,", "410", "U. S.", "113", "(1973)"],
        )
        self.assertEqual(
            tokenize("Foo bar eats grue, 232 Vet. App. (2003)"),
            ["Foo", "bar", "eats", "grue,", "232", "Vet. App.", "(2003)"],
        )
        # Tests that the tokenizer handles whitespace well. In the past, the
        # capital letter P in 5243-P matched the abbreviation for the Pacific
        # reporter ("P"), and the tokenizing would be wrong.
        self.assertEqual(
            tokenize("Failed to recognize 1993 Ct. Sup. 5243-P"),
            ["Failed", "to", "recognize", "1993", "Ct. Sup.", "5243-P"],
        )
        # Tests that the tokenizer handles commas after a reporter. In the
        # past, " U. S. " would match but not " U. S., "
        self.assertEqual(
            tokenize("See Roe v. Wade, 410 U. S., at 113"),
            ["See", "Roe", "v.", "Wade,", "410", "U. S.", ",", "at", "113"],
        )

    def test_find_citations(self):
        """Can we find and make citation objects from strings?"""
        # fmt: off
        test_pairs = (
            # Basic test
            ('1 U.S. 1',
             [FullCitation(volume=1, reporter='U.S.', page=1,
                           canonical_reporter=u'U.S.', lookup_index=0,
                           court='scotus', reporter_index=1,
                           reporter_found='U.S.')]),
            # Basic test of non-case name before citation (should not be found)
            ('lissner test 1 U.S. 1',
             [FullCitation(volume=1, reporter='U.S.', page=1,
                           canonical_reporter=u'U.S.', lookup_index=0,
                           court='scotus', reporter_index=3,
                           reporter_found='U.S.')]),
            # Test with plaintiff and defendant
            ('lissner v. test 1 U.S. 1',
             [FullCitation(plaintiff='lissner', defendant='test', volume=1,
                           reporter='U.S.', page=1, canonical_reporter=u'U.S.',
                           lookup_index=0, court='scotus', reporter_index=4,
                           reporter_found='U.S.')]),
            # Test with plaintiff, defendant and year
            ('lissner v. test 1 U.S. 1 (1982)',
             [FullCitation(plaintiff='lissner', defendant='test', volume=1,
                           reporter='U.S.', page=1, year=1982,
                           canonical_reporter=u'U.S.', lookup_index=0,
                           court='scotus', reporter_index=4,
                           reporter_found='U.S.')]),
            # Test with different reporter than all of above.
            ('bob lissner v. test 1 F.2d 1 (1982)',
             [FullCitation(plaintiff='lissner', defendant='test', volume=1,
                           reporter='F.2d', page=1, year=1982,
                           canonical_reporter=u'F.', lookup_index=0,
                           reporter_index=5, reporter_found='F.2d')]),
            # Test with court and extra information
            ('bob lissner v. test 1 U.S. 12, 347-348 (4th Cir. 1982)',
             [FullCitation(plaintiff='lissner', defendant='test', volume=1,
                           reporter='U.S.', page=12, year=1982,
                           extra=u'347-348', court='ca4',
                           canonical_reporter=u'U.S.', lookup_index=0,
                           reporter_index=5, reporter_found='U.S.')]),
            # Test with text before and after and a variant reporter
            ('asfd 22 U. S. 332 (1975) asdf',
             [FullCitation(volume=22, reporter='U.S.', page=332, year=1975,
                           canonical_reporter=u'U.S.', lookup_index=0,
                           court='scotus', reporter_index=2,
                           reporter_found='U. S.')]),
            # Test with finding reporter when it's a second edition
            ('asdf 22 A.2d 332 asdf',
             [FullCitation(volume=22, reporter='A.2d', page=332,
                           canonical_reporter=u'A.', lookup_index=0,
                           reporter_index=2, reporter_found='A.2d')]),
            # Test if reporter in string will find proper citation string
            ('A.2d 332 11 A.2d 333',
             [FullCitation(volume=11, reporter='A.2d', page=333,
                           canonical_reporter=u'A.', lookup_index=0,
                           reporter_index=3, reporter_found='A.2d')]),
            # Test finding a variant second edition reporter
            ('asdf 22 A. 2d 332 asdf',
             [FullCitation(volume=22, reporter='A.2d', page=332,
                           canonical_reporter=u'A.', lookup_index=0,
                           reporter_index=2, reporter_found='A. 2d')]),
            # Test finding a variant of an edition resolvable by variant alone.
            ('171 Wn.2d 1016',
             [FullCitation(volume=171, reporter='Wash. 2d', page=1016,
                           canonical_reporter=u'Wash.', lookup_index=1,
                           reporter_index=1, reporter_found='Wn.2d')]),
            # Test finding two citations where one of them has abutting
            # punctuation.
            ('2 U.S. 3, 4-5 (3 Atl. 33)',
             [FullCitation(volume=2, reporter="U.S.", page=3, extra=u'4-5',
                           canonical_reporter=u"U.S.", lookup_index=0,
                           reporter_index=1, reporter_found="U.S.",
                           court='scotus'),
              FullCitation(volume=3, reporter="A.", page=33,
                           canonical_reporter=u"A.", lookup_index=0,
                           reporter_index=5, reporter_found="Atl.")]),
            # Test with the page number as a Roman numeral
            ('12 Neb. App. lxiv (2004)',
             [FullCitation(volume=12, reporter='Neb. Ct. App.', page='lxiv',
                           year=2004, canonical_reporter=u'Neb. Ct. App.',
                           lookup_index=0, reporter_index=1,
                           reporter_found='Neb. App.')]),
            # Test with the 'digit-REPORTER-digit' corner-case formatting
            ('2007-NMCERT-008',
             [FullCitation(volume=2007, reporter='NMCERT', page=8,
                           canonical_reporter=u'NMCERT', lookup_index=0,
                           reporter_index=1, reporter_found='NMCERT')]),
            ('2006-Ohio-2095',
             [FullCitation(volume=2006, reporter='Ohio', page=2095,
                           canonical_reporter=u'Ohio', lookup_index=0,
                           reporter_index=1, reporter_found='Ohio')]),
            ('2017 IL App (4th) 160407WC',
             [FullCitation(volume=2017, reporter='IL App (4th)',
                           page='160407WC', canonical_reporter=u'IL App (4th)',
                           lookup_index=0, reporter_index=1,
                           reporter_found='IL App (4th)')]),
            ('2017 IL App (1st) 143684-B',
             [FullCitation(volume=2017, reporter='IL App (1st)',
                           page='143684-B', canonical_reporter=u'IL App (1st)',
                           lookup_index=0, reporter_index=1,
                           reporter_found='IL App (1st)')]),
            # Test first kind of short form citation (meaningless antecedent)
            ('asdf 1 U. S., at 2',
             [ShortformCitation(reporter='U.S.', page=2, volume=1,
                                antecedent_guess='asdf', court='scotus',
                                canonical_reporter=u'U.S.', lookup_index=0,
                                reporter_found='U. S.', reporter_index=2)]),
            # Test second kind of short form citation (meaningful antecedent)
            ('asdf, 1 U. S., at 2',
             [ShortformCitation(reporter='U.S.', page=2, volume=1,
                                antecedent_guess='asdf,', court='scotus',
                                canonical_reporter=u'U.S.', lookup_index=0,
                                reporter_found='U. S.', reporter_index=2)]),
            # Test short form citation with preceding ASCII quotation
            (u'asdf,” 1 U. S., at 2',
             [ShortformCitation(reporter='U.S.', page=2, volume=1,
                                antecedent_guess=u'asdf,”', court='scotus',
                                canonical_reporter=u'U.S.', lookup_index=0,
                                reporter_found='U. S.', reporter_index=2)]),
            # Test short form citation when case name looks like a reporter
            ('Johnson, 1 U. S., at 2',
             [ShortformCitation(reporter='U.S.', page=2, volume=1,
                                antecedent_guess=u'Johnson,', court='scotus',
                                canonical_reporter=u'U.S.', lookup_index=0,
                                reporter_found='U. S.', reporter_index=3)]),
            # Test short form citation with no comma after reporter
            ('asdf, 1 U. S. at 2',
             [ShortformCitation(reporter='U.S.', page=2, volume=1,
                                antecedent_guess='asdf,', court='scotus',
                                canonical_reporter=u'U.S.', lookup_index=0,
                                reporter_found='U. S.', reporter_index=2)]),
            # Test first kind of supra citation (standard kind)
            ('asdf, supra, at 2',
             [SupraCitation(antecedent_guess='asdf,', page=2, volume=None)]),
            # Test second kind of supra citation (with volume)
            ('asdf, 123 supra, at 2',
             [SupraCitation(antecedent_guess='asdf,', page=2, volume=123)]),
            # Test third kind of supra citation (sans page)
            ('asdf, supra, foo bar',
             [SupraCitation(antecedent_guess='asdf,', page=None, volume=None)]),
            # Test third kind of supra citation (with period)
            ('asdf, supra. foo bar',
             [SupraCitation(antecedent_guess='asdf,', page=None, volume=None)]),
            # Test Ibid. citation
            ('foo v. bar 1 U.S. 12. asdf. Ibid. foo bar lorem ipsum.',
             [FullCitation(plaintiff='foo', defendant=u'bar', volume=1,
                           reporter='U.S.', page=12, lookup_index=0,
                           canonical_reporter=u'U.S.', reporter_index=4,
                           reporter_found='U.S.', court='scotus'),
              IdCitation(id_token='Ibid.',
                         after_tokens=['foo', 'bar', 'lorem'])]),
            # Test Id. citation
            ('foo v. bar 1 U.S. 12, 347-348. asdf. Id., at 123. foo bar',
             [FullCitation(plaintiff='foo', defendant=u'bar', volume=1,
                           reporter='U.S.', page=12, lookup_index=0,
                           canonical_reporter=u'U.S.', reporter_index=4,
                           reporter_found='U.S.', court='scotus'),
              IdCitation(id_token='Id.,',
                         after_tokens=['at', '123.', 'foo'])]),
        )
        # fmt: on
        for q, a in test_pairs:
            print "Testing citation extraction for %s..." % q,
            cites_found = get_citations(q)
            self.assertEqual(
                cites_found,
                a,
                msg="%s\n%s\n\n    !=\n\n%s"
                % (
                    q,
                    ",\n".join([str(cite.__dict__) for cite in cites_found]),
                    ",\n".join([str(cite.__dict__) for cite in a]),
                ),
            )
            print "✓"

    def test_find_tc_citations(self):
        """Can we parse tax court citations properly?"""
        # fmt: off
        test_pairs = (
            # Test with atypical formatting for Tax Court Memos
            ('the 1 T.C. No. 233',
             [FullCitation(volume=1, reporter='T.C. No.', page=233,
                           canonical_reporter=u'T.C. No.', lookup_index=0,
                           reporter_index=2, reporter_found='T.C. No.')]),
            ('word T.C. Memo. 2019-233',
             [FullCitation(volume=2019, reporter='T.C. Memo.', page=233,
                           canonical_reporter=u'T.C. Memo.', lookup_index=0,
                           reporter_index=1, reporter_found='T.C. Memo.')]),
            ('something T.C. Summary Opinion 2019-233',
             [FullCitation(volume=2019, reporter='T.C. Summary Opinion', page=233,
                           canonical_reporter=u'T.C. Summary Opinion',
                           lookup_index=0,
                           reporter_index=1,
                           reporter_found='T.C. Summary Opinion')]),
            ('T.C. Summary Opinion 2018-133',
             [FullCitation(volume=2018, reporter='T.C. Summary Opinion', page=133,
                           canonical_reporter=u'T.C. Summary Opinion',
                           lookup_index=0,
                           reporter_index=0,
                           reporter_found='T.C. Summary Opinion')]),
            ('1     UNITED STATES TAX COURT REPORT   (2018)',
             [FullCitation(volume=1, reporter='T.C.', page=2018,
                           canonical_reporter=u'T.C.',
                           lookup_index=0,
                           reporter_index=1,
                           reporter_found='UNITED STATES TAX COURT REPORT')]),
            ('U.S. of A. 1     UNITED STATES TAX COURT REPORT   (2018)',
             [FullCitation(volume=1, reporter='T.C.', page=2018,
                           canonical_reporter=u'T.C.',
                           lookup_index=0,
                           reporter_index=4,
                           reporter_found='UNITED STATES TAX COURT REPORT')]),
            # Added this after failing in production
            ('     202                 140 UNITED STATES TAX COURT REPORTS                                   (200)',
             [FullCitation(volume=140, reporter='T.C.', page=200,
                           canonical_reporter=u'T.C.',
                           lookup_index=0,
                           reporter_index=2,
                           reporter_found='UNITED STATES TAX COURT REPORTS')]),
            ('U.S. 1234 1 U.S. 1',
             [FullCitation(volume=1, reporter='U.S.', page=1,
                           canonical_reporter=u'U.S.',
                           lookup_index=0,
                           reporter_index=3,
                           court='scotus',
                           reporter_found='U.S.')]),
        )
        # fmt: on
        for q, a in test_pairs:
            print "Testing citation extraction for %s..." % q,
            cites_found = get_citations(q)
            self.assertEqual(
                cites_found,
                a,
                msg="%s\n%s\n\n    !=\n\n%s"
                % (
                    q,
                    ",\n".join([str(cite.__dict__) for cite in cites_found]),
                    ",\n".join([str(cite.__dict__) for cite in a]),
                ),
            )
            print "✓"

    def test_date_in_editions(self):
        test_pairs = [
            ("S.E.", 1886, False),
            ("S.E.", 1887, True),
            ("S.E.", 1939, True),
            ("S.E.", 2012, True),
            ("T.C.M.", 1950, True),
            ("T.C.M.", 1940, False),
            ("T.C.M.", date.today().year + 1, False),
        ]
        for pair in test_pairs:
            date_in_reporter = is_date_in_reporter(
                REPORTERS[pair[0]][0]["editions"], pair[1]
            )
            self.assertEqual(
                date_in_reporter,
                pair[2],
                msg='is_date_in_reporter(REPORTERS[%s][0]["editions"], %s) != '
                "%s\nIt's equal to: %s"
                % (pair[0], pair[1], pair[2], date_in_reporter),
            )

    def test_disambiguate_citations(self):
        # fmt: off
        test_pairs = [
            # 1. P.R.R --> Correct abbreviation for a reporter.
            ('1 P.R.R. 1',
             [FullCitation(volume=1, reporter='P.R.R.', page=1,
                           canonical_reporter=u'P.R.R.', lookup_index=0,
                           reporter_index=1, reporter_found='P.R.R.')]),
            # 2. U. S. --> A simple variant to resolve.
            ('1 U. S. 1',
             [FullCitation(volume=1, reporter='U.S.', page=1,
                           canonical_reporter=u'U.S.', lookup_index=0,
                           court='scotus', reporter_index=1,
                           reporter_found='U. S.')]),
            # 3. A.2d --> Not a variant, but needs to be looked up in the
            #    EDITIONS variable.
            ('1 A.2d 1',
             [FullCitation(volume=1, reporter='A.2d', page=1,
                           canonical_reporter=u'A.', lookup_index=0,
                           reporter_index=1, reporter_found='A.2d')]),
            # 4. A. 2d --> An unambiguous variant of an edition
            ('1 A. 2d 1',
             [FullCitation(volume=1, reporter='A.2d', page=1,
                           canonical_reporter=u'A.', lookup_index=0,
                           reporter_index=1, reporter_found='A. 2d')]),
            # 5. P.R. --> A variant of 'Pen. & W.', 'P.R.R.', or 'P.' that's
            #    resolvable by year
            ('1 P.R. 1 (1831)',
             # Of the three, only Pen & W. was being published this year.
             [FullCitation(volume=1, reporter='Pen. & W.', page=1,
                           canonical_reporter=u'Pen. & W.', lookup_index=0,
                           year=1831, reporter_index=1, reporter_found='P.R.')]),
            # 5.1: W.2d --> A variant of an edition that either resolves to
            #      'Wis. 2d' or 'Wash. 2d' and is resolvable by year.
            ('1 W.2d 1 (1854)',
             # Of the two, only Wis. 2d was being published this year.
             [FullCitation(volume=1, reporter='Wis. 2d', page=1,
                           canonical_reporter=u'Wis.', lookup_index=0,
                           year=1854, reporter_index=1, reporter_found='W.2d')]),
            # 5.2: Wash. --> A non-variant that has more than one reporter for
            #      the key, but is resolvable by year
            ('1 Wash. 1 (1890)',
             [FullCitation(volume=1, reporter='Wash.', page=1,
                           canonical_reporter=u'Wash.', lookup_index=1,
                           year=1890, reporter_index=1, reporter_found='Wash.')]),
            # 6. Cr. --> A variant of Cranch, which is ambiguous, except with
            #    paired with this variation.
            ('1 Cra. 1',
             [FullCitation(volume=1, reporter='Cranch', page=1,
                           canonical_reporter=u'Cranch', lookup_index=0,
                           court='scotus', reporter_index=1,
                           reporter_found='Cra.')]),
            # 7. Cranch. --> Not a variant, but could refer to either Cranch's
            #    Supreme Court cases or his DC ones. In this case, we cannot
            #    disambiguate. Years are not known, and we have no further
            #    clues. We must simply drop Cranch from the results.
            ('1 Cranch 1 1 U.S. 23',
             [FullCitation(volume=1, reporter='U.S.', page=23,
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
            # [FullCitation(volume=1, reporter='Rob.', page=1,
            #                          canonical_reporter='Rob.',
            #                          lookup_index=0),
            #  FullCitation(volume=1, reporter='La.', page=1,
            #                          canonical_reporter='La.',
            #                          lookup_index=0)]),
        ]
        # fmt: on
        for pair in test_pairs:
            print "Testing disambiguation for %s..." % pair[0],
            citations = get_citations(pair[0], html=False)
            self.assertEqual(
                citations,
                pair[1],
                msg="%s\n%s != \n%s"
                % (
                    pair[0],
                    [cite.__dict__ for cite in citations],
                    [cite.__dict__ for cite in pair[1]],
                ),
            )
            print "✓"

    def test_make_html(self):
        """Can we make basic HTML conversions properly?"""
        # fmt: off

        full_citation_html = ('<pre class="inline">asdf </pre><span class="'
                              'citation no-link"><span class="volume">22'
                              '</span> <span class="reporter">U.S.</span> '
                              '<span class="page">33</span> </span><pre class='
                              '"inline">asdf</pre>')
        test_pairs = [
            # Simple example for full citations
            ('asdf 22 U.S. 33 asdf', full_citation_html),

            # Using a variant format for U.S. (Issue #409)
            ('asdf 22 U. S. 33 asdf', full_citation_html),

            # Full citation across line break
            ('asdf John v. Doe, 123\nU.S. 456, upholding foo bar',
             '<pre class="inline">asdf John v. Doe, </pre><span class="'
             'citation no-link"><span class="volume">123</span>\n<span class='
             '"reporter">U.S.</span> <span class="page">456</span></span><pre'
             ' class="inline">, upholding foo bar</pre>'),

            # First kind of short form citation (meaningless antecedent)
            ('asdf. 515 U.S., at 240. foobar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf. </span><span class="volume">515</span> '
             '<span class="reporter">U.S.</span>, at <span class="page">240'
             '</span></span><pre class="inline">. foobar</pre>'),

            # Second kind of short form citation (meaningful antecedent)
            ('asdf, 1 U. S., at 2. foobar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf, </span><span class="volume">1</span> '
             '<span class="reporter">U.S.</span>, at <span class="page">2'
             '</span></span><pre class="inline">. foobar</pre>'),

            # Short form citation with no comma after reporter in original
            ('asdf, 1 U. S. at 2. foobar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf, </span><span class="volume">1</span> '
             '<span class="reporter">U.S.</span>, at <span class="page">2'
             '</span></span><pre class="inline">. foobar</pre>'),

            # Short form citation across line break
            (u'asdf.’ ” 123 \n U.S., at 456. Foo bar foobar',
             '<pre class="inline">asdf.’ </pre><span class="citation no-link">'
             '<span class="antecedent">” </span><span class="volume">123'
             '</span> \n <span class="reporter">U.S.</span>, at <span class='
             '"page">456</span></span><pre class="inline">. Foo bar foobar'
             '</pre>'),

            # First kind of supra citation (standard kind)
            ('asdf, supra, at 2. foobar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf,</span><span> supra</span><span>, at '
             '</span><span class="page">2</span></span><pre class="inline">'
             '. foobar</pre>'),

            # Second kind of supra citation (with volume)
            ('asdf, 123 supra, at 2. foo bar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf,</span> <span class="volume">123</span>'
             '<span> supra</span><span>, at </span><span class="page">2</span>'
             '</span><pre class="inline">. foo bar</pre>'),

            # Third kind of supra citation (sans page)
            ('asdf, supra, foo bar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf,</span><span> supra</span></span><pre '
             'class="inline">, foo bar</pre>'),

            # Fourth kind of supra citation (with period)
            ('asdf, supra. foo bar',
             '<pre class="inline"></pre><span class="citation no-link"><span '
             'class="antecedent">asdf,</span><span> supra</span></span><pre '
             'class="inline">. foo bar</pre>'),

            # Supra citation across line break
            ('asdf, supra, at\n99 (quoting foo)',
             '<pre class="inline"></pre><span class="citation no-link"><span'
             ' class="antecedent">asdf,</span><span> supra</span><span>, at\n'
             '</span><span class="page">99</span> </span><pre class="inline">'
             '(quoting foo)</pre>'),

            # First kind of id. citation ("Id., at 123")
            ('asdf, id., at 123. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation no-link">'
             'id.,<span class="after_tokens"> <span class="after_token">at'
             '</span> <span class="after_token">123.</span> <span class="'
             'after_token">Lorem</span> </span></span><pre class="inline">'
             'ipsum dolor sit amet</pre>'),

            # Second kind of id. citation ("Ibid.")
            ('asdf, Ibid. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation no-link">'
             'Ibid.<span class="after_tokens"> <span class="after_token">Lorem'
             '</span> <span class="after_token">ipsum</span> <span class="'
             'after_token">dolor</span> </span></span><pre class="inline">'
             'sit amet</pre>'),

            # Id. citation across line break
            ('asdf." Id., at 315.\n       Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf." </pre><span class="citation no-link">'
             'Id.,<span class="after_tokens"> <span class="after_token">at'
             '</span> <span class="after_token">315.</span>\n       <span'
             ' class="after_token">Lorem</span> </span></span><pre class="'
             'inline">ipsum dolor sit amet</pre>')
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            print "Testing html conversion for %s..." % s,
            opinion = Opinion(plain_text=s)
            citations = get_citations(s)
            created_html = create_cited_html(opinion, citations)
            self.assertEqual(
                created_html,
                expected_html,
                msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
            )
            print "✓"


class MatchingTest(IndexedSolrTestCase):
    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "opinions_matching_citations.json",
    ]

    def test_citation_resolution(self):
        """Tests whether different types of citations (i.e., full, short form,
        supra, id) resolve correctly to opinion matches.
        """
        # fmt: off

        # Opinion fixture info:
        # pk=7 is mocked with name 'Foo v. Bar' and citation '1 U.S. 1'
        # pk=8 is mocked with name 'Qwerty v. Uiop' and citation '2 F.3d 2'
        # pk=9 is mocked with name 'Lorem v. Ipsum' and citation '1 U.S. 50'

        test_pairs = [
            # Simple test for matching a single, full citation
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.')
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test matching multiple full citations to different documents
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=2, reporter='F.3d', page=2,
                             canonical_reporter=u'F.', lookup_index=0,
                             court='ca1', reporter_index=1,
                             reporter_found='F.3d')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=8)
            ]),

            # Test resolving a supra citation
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                SupraCitation(antecedent_guess='Bar', page=99, volume=1)
                ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation with a meaningful antecedent
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page=99, volume=1,
                                  antecedent_guess='Bar,')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates. We expect its antecedent
            # guess to provide the correct tiebreaker.
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page=50,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page=99, volume=1,
                                  antecedent_guess='Bar')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=9),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates, and when it lacks a
            # meaningful antecedent.
            # We expect the short form citation to not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page=50,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page=99, volume=1,
                                  antecedent_guess='somethingwrong')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=9)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume are erroneous.
            # We expect the short form citation to not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='F.3d', page=99, volume=26,
                                  antecedent_guess='somethingwrong')
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation match
            # failed because there is no clear antecedent. We expect the Id.
            # citation to also not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='F.3d', page=99, volume=26,
                                  antecedent_guess='somethingwrong'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation match
            # failed because a normal full citation lookup returned nothing.
            # We expect the Id. citation to also not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page=1,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=99, reporter='U.S.', page=99,
                             canonical_reporter=u'U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7)
            ])
        ]

        # fmt: on
        for citations, expected_matches in test_pairs:
            print "Testing citation matching for %s..." % citations

            # The citing opinion does not matter for this test
            citing_opinion = Opinion.objects.get(pk=1)

            citation_matches = get_citation_matches(citing_opinion, citations)
            self.assertEqual(
                citation_matches,
                expected_matches,
                msg="\n%s\n\n    !=\n\n%s"
                % (citation_matches, expected_matches),
            )
            print "✓"

    def test_citation_matching_issue621(self):
        """Make sure that a citation like 1 Wheat 9 doesn't match 9 Wheat 1"""
        # The fixture contains a reference to 9 F. 1, so we expect no results.
        citation_str = "1 F. 9 (1795)"
        citation = get_citations(citation_str)[0]
        results = match_citation(citation)
        self.assertEqual([], results)


class UpdateTest(IndexedSolrTestCase):
    """Tests whether the update task performs correctly, i.e., whether it
    creates new OpinionsCited objects and whether it updates the citation
    counters.
    """

    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "opinions_matching_citations.json",
    ]

    def test_citation_increment(self):
        """Make sure that found citations update the increment on the cited
        opinion's citation count"""
        remove_citations_from_imported_fixtures()

        # Updates d1's citation count in a Celery task
        find_citations_for_opinion_by_pks.delay([3])

        cited = Opinion.objects.get(pk=2)
        expected_count = 1
        self.assertEqual(
            cited.cluster.citation_count,
            expected_count,
            msg=u"'cited' was not updated by a citation found in 'citing', or "
            u"the citation was not found. Count was: %s instead of %s"
            % (cited.cluster.citation_count, expected_count),
        )

    def test_opinionscited_creation(self):
        """Make sure that found citations are stored in the database as
        OpinionsCited objects with the appropriate references and depth.
        """
        # Opinion fixture info:
        # pk=10 is our mock citing opinion, containing a number of references
        # to other mocked opinions, mixed about. It's hard to exhaustively
        # test all combinations, but this test case is made to be deliberately
        # complex, in an effort to "trick" the algorithm. Cited opinions:
        # pk=7: 1 FullCitation, 1 ShortformCitation, 1 SupraCitation (depth=3)
        # pk=8: 3 FullCitation (one normal, one Id., and one Ibid.),
        #   1 ShortformCitation, 2 SupraCitation (depth=6)
        # pk=9: 1 FullCitation, 1 ShortformCitation (depth=2)
        remove_citations_from_imported_fixtures()
        citing = Opinion.objects.get(pk=10)
        find_citations_for_opinion_by_pks.delay([10])

        test_pairs = [
            (Opinion.objects.get(pk=7), 3),
            (Opinion.objects.get(pk=8), 6),
            (Opinion.objects.get(pk=9), 2),
        ]

        for cited, depth in test_pairs:
            print "Testing OpinionsCited creation for %s..." % cited,
            self.assertEqual(
                OpinionsCited.objects.get(
                    citing_opinion=citing, cited_opinion=cited
                ).depth,
                depth,
            )
            print "✓"


class CitationFeedTest(IndexedSolrTestCase):
    def _tree_has_content(self, content, expected_count):
        xml_tree = etree.fromstring(content)
        count = len(
            xml_tree.xpath(
                "//a:entry", namespaces={"a": "http://www.w3.org/2005/Atom"}
            )
        )
        self.assertEqual(
            count, expected_count,
        )

    def test_basic_cited_by_feed(self):
        """Can we load the cited-by feed and does it have content?"""
        r = self.client.get(
            reverse("search_feed", args=["search"]), {"q": "cites:1"}
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)

    def test_unicode_content(self):
        """Does the citation feed continue working even when we have a unicode
        case name?
        """
        new_case_name = (
            u"MAC ARTHUR KAMMUELLER, \u2014 v. LOOMIS, FARGO & " u"CO., \u2014"
        )
        OpinionCluster.objects.filter(pk=1).update(case_name=new_case_name)

        r = self.client.get(
            reverse("search_feed", args=["search"]), {"q": "cites:1"},
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)


class CitationCommandTest(IndexedSolrTestCase):
    """Test a variety of the ways that cl_find_citations can be called."""

    def call_command_and_test_it(self, args):
        remove_citations_from_imported_fixtures()
        call_command("cl_find_citations", *args)
        cited = Opinion.objects.get(pk=2)
        expected_count = 1
        self.assertEqual(
            cited.cluster.citation_count,
            expected_count,
            msg=u"'cited' was not updated by a citation found in 'citing', or "
            u"the citation was not found. Count was: %s instead of %s"
            % (cited.cluster.citation_count, expected_count),
        )

    def test_index_by_doc_id(self):
        args = [
            "--doc_id",
            "3",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_doc_ids(self):
        args = [
            "--doc_id",
            "3",
            "2",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_only(self):
        args = [
            "--start_id",
            "0",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_and_end(self):
        args = [
            "--start_id",
            "0",
            "--end_id",
            "5",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_filed_after(self):
        args = [
            "--filed_after",
            "2015-06-09",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)


class ParallelCitationTest(SimpleTestCase):
    allow_database_queries = True

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
                "not %s."
                % (computed_num_citation_groups, citation_group_count),
            )
            if not citation_groups:
                # Add an empty list to make testing easier.
                citation_groups = [[]]
            computed_num_parallel_citation = len(list(citation_groups)[0])
            self.assertEqual(
                computed_num_parallel_citation,
                expected_num_parallel_citations,
                msg="Did not identify correct number of parallel citations in "
                "the group. Got %s, not %s"
                % (
                    computed_num_parallel_citation,
                    expected_num_parallel_citations,
                ),
            )
            print "✓"

    def test_making_edge_list(self):
        """Can we make networkx-friendly edge lists?"""
        tests = [
            ([1, 2], [(1, 2)]),
            ([1, 2, 3], [(1, 2), (2, 3)]),
            ([1, 2, 3, 4], [(1, 2), (2, 3), (3, 4)]),
        ]
        for q, a in tests:
            self.assertEqual(
                make_edge_list(q), a,
            )

    def test_hash(self):
        """Do two citation objects hash to the same?"""
        Citation.__hash__ = Citation.fuzzy_hash
        citations = [
            Citation(reporter=2, volume="U.S.", page="2", reporter_index=1),
            Citation(reporter=2, volume="U.S.", page="2", reporter_index=2),
        ]
        self.assertEqual(
            hash(citations[0]), hash(citations[1]),
        )
        Citation.fuzzy_hash = Citation.__hash__
