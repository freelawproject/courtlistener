from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from eyecite import get_citations
from eyecite.test_factories import (
    case_citation,
    id_citation,
    nonopinion_citation,
    supra_citation,
)
from lxml import etree

from cl.citations.annotate_citations import (
    create_cited_html,
    get_and_clean_opinion_text,
)
from cl.citations.management.commands.cl_add_parallel_citations import (
    identify_parallel_citations,
    make_edge_list,
)
from cl.citations.match_citations import get_citation_matches, match_citation
from cl.citations.tasks import find_citations_for_opinion_by_pks
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.search.models import Opinion, OpinionCluster, OpinionsCited


def remove_citations_from_imported_fixtures():
    """Delete all the connections between items that are in the fixtures by
    default, and reset counts to zero.
    """
    OpinionsCited.objects.all().delete()
    OpinionCluster.objects.all().update(citation_count=0)


class CiteTest(TestCase):
    def test_make_html_from_plain_text(self) -> None:
        """Can we convert the plain text of an opinion into HTML?"""
        # fmt: off

        test_pairs = [
            # Simple example for full citations
            ('asdf 22 U.S. 33 asdf',
             '<pre class="inline">asdf </pre><span class="'
             'citation no-link">22 U.S. 33</span><pre class="'
             'inline"> asdf</pre>'),

            # Using a variant format for U.S. (Issue #409)
            ('asdf 22 U. S. 33 asdf',
             '<pre class="inline">asdf </pre><span class="'
             'citation no-link">22 U. S. 33</span><pre class="'
             'inline"> asdf</pre>'),

            # Full citation across line break
            ('asdf John v. Doe, 123\nU.S. 456, upholding foo bar',
             '<pre class="inline">asdf John v. Doe, </pre><span class="'
             'citation no-link">123\nU.S. 456</span><pre class="inline">, '
             'upholding foo bar</pre>'),

            # Basic short form citation
            ('existing text asdf, 515 U.S., at 240. foobar',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">515 U.S., at 240</span><pre class="inline">. '
             'foobar</pre>'),

            # Short form citation with no comma after reporter in original
            ('existing text asdf, 1 U. S. at 2. foobar',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">1 U. S. at 2</span><pre class="inline">. '
             'foobar</pre>'),

            # Short form citation across line break
            ('asdf.’ ” 123 \n U.S., at 456. Foo bar foobar',
             '<pre class="inline">asdf.’ ” </pre><span class="citation '
             'no-link">123 \n U.S., at 456</span><pre class="inline">. Foo '
             'bar foobar</pre>'),

            # First kind of supra citation (standard kind)
            ('existing text asdf, supra, at 2. foobar',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">supra, at 2</span><pre class="inline">. '
             'foobar</pre>'),

            # Second kind of supra citation (with volume)
            ('existing text asdf, 123 supra, at 2. foo bar',
             '<pre class="inline">existing text asdf, 123 </pre><span class="'
             'citation no-link">supra, at 2</span><pre class="inline">. foo '
             'bar</pre>'),

            # Third kind of supra citation (sans page)
            ('existing text asdf, supra, foo bar',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">supra,</span><pre class="inline"> foo bar'
             '</pre>'),

            # Fourth kind of supra citation (with period)
            ('existing text asdf, supra. foo bar',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">supra.</span><pre class="inline"> foo bar'
             '</pre>'),

            # Supra citation across line break
            ('existing text asdf, supra, at\n99 (quoting foo)',
             '<pre class="inline">existing text asdf, </pre><span class="'
             'citation no-link">supra, at\n99</span><pre class="inline"> '
             '(quoting foo)</pre>'),

            # Id. citation ("Id., at 123")
            ('asdf, id., at 123. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation no-link">'
             'id., at 123</span><pre class="inline">. Lorem ipsum dolor sit '
             'amet</pre>'),

            # Duplicate Id. citation
            ('asd, id., at 123. Lo rem ip sum. asdf, id., at 123. Lo rem ip.',
             '<pre class="inline">asd, </pre><span class="citation no-link">'
             'id., at 123</span><pre class="inline">. Lo rem ip sum. asdf, '
             '</pre><span class="citation no-link">id., at 123</span><pre '
             'class="inline">. Lo rem ip.</pre>'),

            # Id. citation across line break
            ('asdf." Id., at 315.\n       Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf." </pre><span class="citation '
             'no-link">Id., at 315</span><pre class="inline">.\n       Lorem '
             'ipsum dolor sit amet</pre>'),

            # Ibid. citation ("... Ibid.")
            ('asdf, Ibid. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation no-link">'
             'Ibid.</span><pre class="inline"> Lorem ipsum dolor sit amet'
             '</pre>'),

            # NonopinionCitation (currently nothing should happen here)
            ('Lorem ipsum dolor sit amet. U.S. Code §3617. Foo bar.',
             '<pre class="inline">Lorem ipsum dolor sit amet. U.S. Code '
             '§3617. Foo bar.</pre>'),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            with self.subTest(
                "Testing plain text to html conversion for %s..." % s,
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(plain_text=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)
                created_html = create_cited_html(
                    opinion=opinion,
                    citations=citations,
                )
                self.assertEqual(
                    created_html,
                    expected_html,
                    msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
                )

    def test_make_html_from_html(self) -> None:
        """Can we convert the HTML of an opinion into modified HTML?"""
        # fmt: off

        test_pairs = [
            # Id. citation with HTML tags
            ('<div><p>the improper views of the Legislature.\" 2 <i>id., at '
             '73.</i></p>\n<p>Nathaniel Gorham of Massachusetts</p></div>',
             '<div><p>the improper views of the Legislature." 2 <i><span '
             'class="citation no-link">id., at 73</span>.</i></p>\n<p>'
             'Nathaniel Gorham of Massachusetts</p></div>'),

            # Id. citation with an intervening HTML tag
            #  (We expect the HTML to be unchanged, since it's too risky to
            #   modify with another tag in the way)
            ('<div><p>the improper views of the Legislature.\" 2 <i>id.,</i> '
             'at <b>73, bolded</b>.</p>\n<p>Nathaniel Gorham of Massachusetts'
             '</p></div>',
             '<div><p>the improper views of the Legislature.\" 2 <i>id.,</i> '
             'at <b>73, bolded</b>.</p>\n<p>Nathaniel Gorham of Massachusetts'
             '</p></div>'),

            # Ibid. citation with HTML tags
            ('<div><p>possess any peculiar knowledge of the mere policy of '
             'public measures.\" <i>Ibid.</i> Gerry of Massachusetts '
             'like</p></div>',
             '<div><p>possess any peculiar knowledge of the mere policy of '
             'public measures." <i><span class="citation no-link">Ibid.'
             '</span></i> Gerry of Massachusetts like</p></div>'
            ),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            with self.subTest(
                "Testing html to html conversion for %s..." % s,
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(html=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)
                created_html = create_cited_html(
                    opinion=opinion,
                    citations=citations,
                )
                self.assertEqual(
                    created_html,
                    expected_html,
                    msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
                )

    def test_make_html_from_matched_citation_objects(self) -> None:
        """Can we render matched citation objects as HTML?"""
        # This test case is similar to the two above, except it allows us to
        # test the rendering of citation objects that we assert are correctly
        # matched. (No matching is performed in the previous cases.)
        # fmt: off

        test_pairs = [
            # Id. citation with page number ("Id., at 123, 124")
            ('asdf, Id., at 123, 124. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation" data-id="'
             'MATCH_ID"><a href="MATCH_URL">Id., at 123, 124</a></span><pre '
             'class="inline">. Lorem ipsum dolor sit amet</pre>'),

            # Id. citation with complex page number ("Id. @ 123:1, ¶¶ 124")
            ('asdf, Id. @ 123:1, ¶¶ 124. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation" data-id='
             '"MATCH_ID"><a href="MATCH_URL">Id.</a></span><pre class='
             '"inline"> @ 123:1, ¶¶ 124. Lorem ipsum dolor sit amet</pre>'),

            # Id. citation without page number ("Id. Something else")
            ('asdf, Id. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation" data-id="'
             'MATCH_ID"><a href="MATCH_URL">Id.</a></span><pre class="inline">'
             ' Lorem ipsum dolor sit amet</pre>'),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            with self.subTest(
                "Testing object to HTML rendering for %s..." % s,
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(plain_text=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)
                for c in citations:  # Fake correct matching for the citations
                    c.match_url = "MATCH_URL"
                    c.match_id = "MATCH_ID"
                created_html = create_cited_html(
                    opinion=opinion,
                    citations=citations,
                )
                self.assertEqual(
                    created_html,
                    expected_html,
                    msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
                )


class MatchingTest(IndexedSolrTestCase):
    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "opinions_matching_citations.json",
    ]

    def test_citation_resolution(self) -> None:
        """Tests whether different types of citations (i.e., full, short form,
        supra, id) resolve correctly to opinion matches.
        """
        # fmt: off

        # Opinion fixture info:
        # pk=7 is mocked with name 'Foo v. Bar' and citation '1 U.S. 1'
        # pk=8 is mocked with name 'Qwerty v. Uiop' and citation '2 F.3d 2'
        # pk=9 is mocked with name 'Lorem v. Ipsum' and citation '1 U.S. 50'
        # pk=11 is mocked with name 'Abcdef v. Ipsum' and citation '1 U.S. 999'

        test_pairs = [
            # Simple test for matching a single, full citation
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.')
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test matching multiple full citations to different documents
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='2', reporter='F.3d', page='2',
                              canonical_reporter='F.',
                              court='ca1', index=1,
                              reporter_found='F.3d')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=8)
            ]),

            # Test resolving a supra citation
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                supra_citation(index=1, antecedent_guess='Bar', pin_cite='99',
                               volume='1')
                ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a supra citation when its antecedent guess matches
            # two possible candidates. We expect the supra citation to not
            # be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='50',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='1', reporter='U.S.', page='999',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                supra_citation(index=1, antecedent_guess='Ipsum', pin_cite='99',
                               volume='1')
                ], [
                Opinion.objects.get(pk=9),
                Opinion.objects.get(pk=11)
            ]),

            # Test resolving a supra citation when its antecedent guess is
            # None. We it expect it not to be matched, but not to crash.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                supra_citation(index=1, antecedent_guess=None, pin_cite='99',
                               volume='1')
                ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation with a meaningful antecedent
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='U.S.', page='99', volume='1', index=1,
                              antecedent_guess='Bar,', short=True)
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates. We expect its antecedent
            # guess to provide the correct tiebreaker.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='1', reporter='U.S.', page='50',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='U.S.', page='99', volume='1', index=1,
                              antecedent_guess='Bar', short=True)
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
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='1', reporter='U.S.', page='50',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='U.S.', page='99', volume='1', index=1,
                              antecedent_guess='somethingwrong', short=True)
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=9)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates, and when its antecedent
            # guess also matches multiple possibilities.
            # We expect the short form citation to not be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='50',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='1', reporter='U.S.', page='999',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='U.S.', page='99', volume='1', index=1,
                              antecedent_guess='Ipsum', short=True)
            ], [
                Opinion.objects.get(pk=9),
                Opinion.objects.get(pk=11)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume are erroneous.
            # We expect the short form citation to not be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='F.3d', page='99', volume='1', index=1,
                              antecedent_guess='somethingwrong', short=True)
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                id_citation(index=1)
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation match
            # failed because there is no clear antecedent. We expect the Id.
            # citation to also not be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(reporter='F.3d', page='99', volume='1', index=1,
                              antecedent_guess='somethingwrong', short=True),
                id_citation(index=1)
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation match
            # failed because a normal full citation lookup returned nothing.
            # We expect the Id. citation to also not be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                case_citation(volume='1', reporter='U.S.', page='99',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                id_citation(index=1)
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation is to a
            # non-opinion document. Since we can't match those documents (yet),
            # we expect the Id. citation to also not be matched.
            ([
                case_citation(volume='1', reporter='U.S.', page='1',
                              canonical_reporter='U.S.',
                              court='scotus', index=1,
                              reporter_found='U.S.'),
                nonopinion_citation(index=1, source_text='§99'),
                id_citation(index=1)
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when it is the first citation
            # found. Since there is nothing before it, we expect no matches to
            # be returned.
            ([
                id_citation(index=1)
            ], [])
        ]

        # fmt: on
        for citations, expected_matches in test_pairs:
            with self.subTest(
                "Testing citation matching for %s..." % citations,
                citations=citations,
                expected_matches=expected_matches,
            ):
                # The citing opinion does not matter for this test
                citing_opinion = Opinion.objects.get(pk=1)

                citation_matches = get_citation_matches(
                    citing_opinion, citations
                )
                self.assertEqual(
                    citation_matches,
                    expected_matches,
                    msg="\n%s\n\n    !=\n\n%s"
                    % (citation_matches, expected_matches),
                )

    def test_citation_matching_issue621(self) -> None:
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

    def test_citation_increment(self) -> None:
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
            msg="'cited' was not updated by a citation found in 'citing', or "
            "the citation was not found. Count was: %s instead of %s"
            % (cited.cluster.citation_count, expected_count),
        )

    def test_opinionscited_creation(self) -> None:
        """Make sure that found citations are stored in the database as
        OpinionsCited objects with the appropriate references and depth.
        """
        # Opinion fixture info:
        # pk=10 is our mock citing opinion, containing a number of references
        # to other mocked opinions, mixed about. It's hard to exhaustively
        # test all combinations, but this test case is made to be deliberately
        # complex, in an effort to "trick" the algorithm. Cited opinions:
        # pk=7: 1 FullCaseCitation, 1 ShortCaseCitation, 1 SupraCitation (depth=3)
        # pk=8: 1 FullCaseCitation, 2 IdCitation (one Id. and one Ibid.),
        #   1 ShortCaseCitation, 2 SupraCitation (depth=6)
        # pk=9: 1 FullCaseCitation, 1 ShortCaseCitation (depth=2)
        remove_citations_from_imported_fixtures()
        citing = Opinion.objects.get(pk=10)
        find_citations_for_opinion_by_pks.delay([10])

        test_pairs = [
            (Opinion.objects.get(pk=7), 3),
            (Opinion.objects.get(pk=8), 6),
            (Opinion.objects.get(pk=9), 2),
        ]

        for cited, depth in test_pairs:
            with self.subTest(
                "Testing OpinionsCited creation for %s..." % cited,
                cited=cited,
                depth=depth,
            ):
                self.assertEqual(
                    OpinionsCited.objects.get(
                        citing_opinion=citing, cited_opinion=cited
                    ).depth,
                    depth,
                )


class CitationFeedTest(IndexedSolrTestCase):
    def _tree_has_content(self, content, expected_count):
        xml_tree = etree.fromstring(content)
        count = len(
            xml_tree.xpath(
                "//a:entry", namespaces={"a": "http://www.w3.org/2005/Atom"}
            )
        )
        self.assertEqual(count, expected_count)

    def test_basic_cited_by_feed(self) -> None:
        """Can we load the cited-by feed and does it have content?"""
        r = self.client.get(
            reverse("search_feed", args=["search"]), {"q": "cites:1"}
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)

    def test_unicode_content(self) -> None:
        """Does the citation feed continue working even when we have a unicode
        case name?
        """
        new_case_name = (
            "MAC ARTHUR KAMMUELLER, \u2014 v. LOOMIS, FARGO & " "CO., \u2014"
        )
        OpinionCluster.objects.filter(pk=1).update(case_name=new_case_name)

        r = self.client.get(
            reverse("search_feed", args=["search"]), {"q": "cites:1"}
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
            msg="'cited' was not updated by a citation found in 'citing', or "
            "the citation was not found. Count was: %s instead of %s"
            % (cited.cluster.citation_count, expected_count),
        )

    def test_index_by_doc_id(self) -> None:
        args = [
            "--doc-id",
            "3",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_doc_ids(self) -> None:
        args = [
            "--doc-id",
            "3",
            "2",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_only(self) -> None:
        args = [
            "--start-id",
            "0",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_and_end(self) -> None:
        args = [
            "--start-id",
            "0",
            "--end-id",
            "5",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_filed_after(self) -> None:
        args = [
            "--filed-after",
            "2015-06-09",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)


class ParallelCitationTest(SimpleTestCase):
    databases = "__all__"

    def test_identifying_parallel_citations(self) -> None:
        """Given a string, can we identify parallel citations"""
        tests = (
            # A pair consisting of a test string and the number of parallel
            # citations that should be identifiable in that string.
            # Simple case
            ("1 U.S. 1 (22 U.S. 33)", 1, 2),
            # Too far apart
            ("1 U.S. 1 too many words 22 U.S. 33", 0, 0),
            # Three citations
            # ("1 U.S. 1, (44 U.S. 33, 99 U.S. 100)", 1, 3),
            # Parallel citation after a valid citation too early on
            ("1 U.S. 1 too many words, then 22 U.S. 33, 13 WL 33223", 1, 2),
        )
        for q, citation_group_count, expected_num_parallel_citations in tests:
            with self.subTest(
                "Testing parallel citation identification for: %s..." % q,
                q=q,
                citation_group_count=citation_group_count,
                expected_num_parallel_citations=expected_num_parallel_citations,
            ):
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

    def test_making_edge_list(self) -> None:
        """Can we make network-friendly edge lists?"""
        tests = [
            ([1, 2], [(1, 2)]),
            ([1, 2, 3], [(1, 2), (2, 3)]),
            ([1, 2, 3, 4], [(1, 2), (2, 3), (3, 4)]),
        ]
        for q, a in tests:
            with self.subTest(
                "Testing network-friendly edge creation for: %s..." % q,
                q=q,
                a=a,
            ):
                self.assertEqual(make_edge_list(q), a)
