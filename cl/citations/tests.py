from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from eyecite.find_citations import get_citations
from eyecite.models import (
    FullCitation,
    IdCitation,
    NonopinionCitation,
    ShortformCitation,
    SupraCitation,
)
from lxml import etree

from cl.citations.management.commands.cl_add_parallel_citations import (
    identify_parallel_citations,
    make_edge_list,
)
from cl.citations.match_citations import get_citation_matches, match_citation
from cl.citations.tasks import (
    create_cited_html,
    find_citations_for_opinion_by_pks,
)
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

            # Basic short form citation
            ('existing text asdf, 515 U.S., at 240. foobar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> <span '
             'class="volume">515</span> <span class="reporter">U.S.</span>, '
             'at <span class="page">240</span></span><pre class="inline">. '
             'foobar</pre>'),

            # Short form citation with no comma after reporter in original
            ('existing text asdf, 1 U. S. at 2. foobar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> <span class'
             '="volume">1</span> <span class="reporter">U.S.</span> at <span '
             'class="page">2</span></span><pre class="inline">. foobar</pre>'),

            # Short form citation across line break
            ('asdf.’ ” 123 \n U.S., at 456. Foo bar foobar',
             '<pre class="inline">asdf.’ </pre><span class="'
             'citation no-link"><span class="antecedent_guess">”'
             '</span> <span class="volume">123</span> \n <span class='
             '"reporter">U.S.</span>, at <span class="page">456</span></span>'
             '<pre class="inline">. Foo bar foobar</pre>'),

            # First kind of supra citation (standard kind)
            ('existing text asdf, supra, at 2. foobar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> supra, at '
             '<span class="page">2</span></span><pre class="inline">. foobar'
             '</pre>'),

            # Second kind of supra citation (with volume)
            ('existing text asdf, 123 supra, at 2. foo bar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> <span '
             'class="volume">123</span> supra, at <span class="page">2</span>'
             '</span><pre class="inline">. foo bar</pre>'),

            # Third kind of supra citation (sans page)
            ('existing text asdf, supra, foo bar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> supra'
             '</span><pre class="inline">, foo bar</pre>'),

            # Fourth kind of supra citation (with period)
            ('existing text asdf, supra. foo bar',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> supra'
             '</span><pre class="inline">. foo bar</pre>'),

            # Supra citation across line break
            ('existing text asdf, supra, at\n99 (quoting foo)',
             '<pre class="inline">existing text </pre><span class="citation '
             'no-link"><span class="antecedent_guess">asdf,</span> supra, '
             'at\n<span class="page">99</span> </span><pre class="inline">'
             '(quoting foo)</pre>'),

            # Id. citation ("Id., at 123")
            ('asdf, id., at 123. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf</pre><span class="citation no-link">, '
             '<span class="id_token">id.,</span> at 123. </span><pre class="'
             'inline">Lorem ipsum dolor sit amet</pre>'),

            # Duplicate Id. citation
            ('asd, id., at 123. Lo rem ip sum. asdf, id., at 123. Lo rem ip.',
             '<pre class="inline">asd</pre><span class="citation no-link">, '
             '<span class="id_token">id.,</span> at 123. </span><pre class="'
             'inline">Lo rem ip sum. asdf</pre><span class="citation '
             'no-link">, <span class="id_token">id.,</span> at 123. </span>'
             '<pre class="inline">Lo rem ip.</pre>'),

            # Id. citation across line break
            ('asdf." Id., at 315.\n       Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf."</pre><span class="citation no-link"> '
             '<span class="id_token">Id.,</span> at 315.\n</span><pre class="'
             'inline">       Lorem ipsum dolor sit amet</pre>'),

            # Ibid. citation ("... Ibid.")
            ('asdf, Ibid. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf</pre><span class="citation no-link">, '
             '<span class="id_token">Ibid.</span> Lorem ipsum dolor </span>'
             '<pre class="inline">sit amet</pre>'),

            # NonopinionCitation (currently nothing should happen here)
            ('Lorem ipsum dolor sit amet. U.S. Code §3617. Foo bar.',
             '<pre class="inline">Lorem ipsum dolor sit amet. U.S. Code '
             '§3617. Foo bar.</pre>'),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            print(
                "Testing plain text to html conversion for %s..." % s, end=" "
            )
            opinion = Opinion(plain_text=s)
            citations = get_citations(s)
            created_html = create_cited_html(opinion, citations)
            self.assertEqual(
                created_html,
                expected_html,
                msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
            )
            print("✓")

    def test_make_html_from_html(self) -> None:
        """Can we convert the HTML of an opinion into modified HTML?"""
        # fmt: off

        test_pairs = [
            # Id. citation with HTML tags
            ('<div><p>the improper views of the Legislature.\" 2 <i>id.,</i> '
             'at 73.</p>\n<p>Nathaniel Gorham of Massachusetts</p></div>',
             '<div><p>the improper views of the Legislature." 2<span class="'
             'citation no-link"> <i><span class="id_token">id.,</span></i> at '
             '73.</span></p>\n<p>Nathaniel Gorham of Massachusetts</p></div>'),

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
             'public measures."<span class="citation no-link"> <i><span class='
             '"id_token">Ibid.</span></i> Gerry of Massachusetts </span>like'
             '</p></div>'
            ),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            print("Testing html to html conversion for %s..." % s, end=" ")
            opinion = Opinion(html=s)
            citations = get_citations(s, clean=("html", "whitespace"))
            created_html = create_cited_html(opinion, citations)
            self.assertEqual(
                created_html,
                expected_html,
                msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
            )
            print("✓")

    def test_make_html_from_matched_citation_objects(self) -> None:
        """Can we render matched citation objects as HTML?"""
        # This test case is similar to the two above, except it allows us to
        # test the rendering of citation objects that we assert are correctly
        # matched. (No matching is performed in the previous cases.)
        # fmt: off

        test_triples = [
            # Id. citation with page number ("Id., at 123, 124")
            ('asdf, Id., at 123, 124. Lorem ipsum dolor sit amet',
             IdCitation(id_token='Id.,', after_tokens=['at', '123', '124'],
                        has_page=True),
             '<pre class="inline">asdf</pre><span class="citation" data-id="'
             'MATCH_ID">, <a href="MATCH_URL"><span class="id_token">Id.,'
             '</span> at 123, 124</a></span><pre class="inline">. Lorem ipsum'
             ' dolor sit amet</pre>'),

            # Id. citation with complex page number ("Id. @ 123:1, ¶¶ 124")
            ('asdf, Id. @ 123:1, ¶¶ 124. Lorem ipsum dolor sit amet',
             IdCitation(id_token='Id.',
                        after_tokens=['@', '123:1', '¶¶', '124'],
                        has_page=True),
             '<pre class="inline">asdf</pre><span class="citation" data-id="'
             'MATCH_ID">, <a href="MATCH_URL"><span class="id_token">Id.'
             '</span> @ 123:1, ¶¶ 124</a></span><pre class="inline">. Lorem '
             'ipsum dolor sit amet</pre>'),

            # Id. citation without page number ("Id. Something else")
            ('asdf, Id. Lorem ipsum dolor sit amet',
             IdCitation(id_token='Id.', after_tokens=['Lorem', 'ipsum'],
                        has_page=False),
             '<pre class="inline">asdf</pre><span class="citation" data-id='
             '"MATCH_ID">, <a href="MATCH_URL"><span class="id_token">Id.'
             '</span></a> Lorem ipsum </span><pre class="inline">dolor sit '
             'amet</pre>'),
        ]

        # fmt: on
        for plain_text, citation, expected_html in test_triples:
            print(
                "Testing object to HTML rendering for %s..." % plain_text,
                end=" ",
            )
            citation.match_url = "MATCH_URL"
            citation.match_id = "MATCH_ID"
            opinion = Opinion(plain_text=plain_text)
            created_html = create_cited_html(opinion, [citation])
            self.assertEqual(
                created_html,
                expected_html,
                msg="\n%s\n\n    !=\n\n%s" % (created_html, expected_html),
            )
            print("✓")


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
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.')
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test matching multiple full citations to different documents
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=2, reporter='F.3d', page='2',
                             canonical_reporter='F.', lookup_index=0,
                             court='ca1', reporter_index=1,
                             reporter_found='F.3d')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=8)
            ]),

            # Test resolving a supra citation
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                SupraCitation(antecedent_guess='Bar', page='99', volume=1)
                ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a supra citation when its antecedent guess matches
            # two possible candidates. We expect the supra citation to not
            # be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page='50',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page='999',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                SupraCitation(antecedent_guess='Ipsum', page='99', volume=1)
                ], [
                Opinion.objects.get(pk=9),
                Opinion.objects.get(pk=11)
            ]),

            # Test resolving a short form citation with a meaningful antecedent
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page='99', volume=1,
                                  antecedent_guess='Bar,')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates. We expect its antecedent
            # guess to provide the correct tiebreaker.
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page='50',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page='99', volume=1,
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
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page='50',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page='99', volume=1,
                                  antecedent_guess='somethingwrong')
            ], [
                Opinion.objects.get(pk=7),
                Opinion.objects.get(pk=9)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates, and when its antecedent
            # guess also matches multiple possibilities.
            # We expect the short form citation to not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page='50',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=1, reporter='U.S.', page='999',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='U.S.', page='99', volume=1,
                                  antecedent_guess='Ipsum')
            ], [
                Opinion.objects.get(pk=9),
                Opinion.objects.get(pk=11)
            ]),

            # Test resolving a short form citation when its reporter and
            # volume are erroneous.
            # We expect the short form citation to not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='F.3d', page='99', volume=26,
                                  antecedent_guess='somethingwrong')
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
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
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                ShortformCitation(reporter='F.3d', page='99', volume=26,
                                  antecedent_guess='somethingwrong'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation match
            # failed because a normal full citation lookup returned nothing.
            # We expect the Id. citation to also not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                FullCitation(volume=99, reporter='U.S.', page='99',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when the previous citation is to a
            # non-opinion document. Since we can't match those documents (yet),
            # we expect the Id. citation to also not be matched.
            ([
                FullCitation(volume=1, reporter='U.S.', page='1',
                             canonical_reporter='U.S.', lookup_index=0,
                             court='scotus', reporter_index=1,
                             reporter_found='U.S.'),
                NonopinionCitation(match_token='§99'),
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [
                Opinion.objects.get(pk=7)
            ]),

            # Test resolving an Id. citation when it is the first citation
            # found. Since there is nothing before it, we expect no matches to
            # be returned.
            ([
                IdCitation(id_token='id.', after_tokens=['a', 'b', 'c'])
            ], [])
        ]

        # fmt: on
        for citations, expected_matches in test_pairs:
            print("Testing citation matching for %s..." % citations)

            # The citing opinion does not matter for this test
            citing_opinion = Opinion.objects.get(pk=1)

            citation_matches = get_citation_matches(citing_opinion, citations)
            self.assertEqual(
                citation_matches,
                expected_matches,
                msg="\n%s\n\n    !=\n\n%s"
                % (citation_matches, expected_matches),
            )
            print("✓")

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
            print("Testing OpinionsCited creation for %s..." % cited, end=" ")
            self.assertEqual(
                OpinionsCited.objects.get(
                    citing_opinion=citing, cited_opinion=cited
                ).depth,
                depth,
            )
            print("✓")


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
            ("1 U.S. 1, (44 U.S. 33, 99 U.S. 100)", 1, 3),
            # Parallel citation after a valid citation too early on
            ("1 U.S. 1 too many words, then 22 U.S. 33, 13 WL 33223", 1, 2),
        )
        for q, citation_group_count, expected_num_parallel_citations in tests:
            print(
                "Testing parallel citation identification for: %s..." % q,
                end=" ",
            )
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
            print("✓")

    def test_making_edge_list(self) -> None:
        """Can we make networkx-friendly edge lists?"""
        tests = [
            ([1, 2], [(1, 2)]),
            ([1, 2, 3], [(1, 2), (2, 3)]),
            ([1, 2, 3, 4], [(1, 2), (2, 3), (3, 4)]),
        ]
        for q, a in tests:
            self.assertEqual(make_edge_list(q), a)
