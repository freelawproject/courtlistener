import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple
from unittest.mock import Mock

from django.core.management import call_command
from django.urls import reverse
from eyecite import get_citations
from eyecite.test_factories import (
    case_citation,
    id_citation,
    journal_citation,
    law_citation,
    nonopinion_citation,
    supra_citation,
)
from factory import RelatedFactory
from lxml import etree

from cl.citations.annotate_citations import (
    create_cited_html,
    get_and_clean_opinion_text,
)
from cl.citations.filter_parentheticals import (
    clean_parenthetical_text,
    is_parenthetical_descriptive,
)
from cl.citations.group_parentheticals import (
    compute_parenthetical_groups,
    get_graph_component,
    get_parenthetical_tokens,
    get_representative_parenthetical,
)
from cl.citations.management.commands.add_parallel_citations import (
    identify_parallel_citations,
    make_edge_list,
)
from cl.citations.match_citations import (
    NO_MATCH_RESOURCE,
    do_resolve_citations,
    resolve_fullcase_citation,
)
from cl.citations.score_parentheticals import parenthetical_score
from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
    store_recap_citations,
)
from cl.lib.test_helpers import (
    CourtTestCase,
    IndexedSolrTestCase,
    PeopleTestCase,
    SearchTestCase,
)
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionWithChildrenFactory,
    RECAPDocumentFactory,
)
from cl.search.models import (
    SEARCH_TYPES,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OpinionsCitedByRECAPDocument,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
)
from cl.tests.cases import ESIndexTestCase, SimpleTestCase, TestCase


class CitationTextTest(SimpleTestCase):
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
             '<pre class="inline">asdf.&quot; </pre><span class="citation '
             'no-link">Id., at 315</span><pre class="inline">.\n       Lorem '
             'ipsum dolor sit amet</pre>'),

            # Ibid. citation ("... Ibid.")
            ('asdf, Ibid. Lorem ipsum dolor sit amet',
             '<pre class="inline">asdf, </pre><span class="citation no-link">'
             'Ibid.</span><pre class="inline"> Lorem ipsum dolor sit amet'
             '</pre>'),

            # NonopinionCitation
            ('Lorem ipsum dolor sit amet. U.S. Code §3617. Foo bar.',
             '<pre class="inline">Lorem ipsum dolor sit amet. U.S. Code </pre>'
             '<span class="citation no-link">§3617.</span><pre class="inline">'
             ' Foo bar.</pre>'),

            # Plaintext with HTML text (see Alexis Hunley v. Instagram, LLC)
            ('<script async src="//www.instagram.com/embed.js"></script>',
             '<pre class="inline">&lt;script async src=&quot;//www.instagram.com/embed.js&quot;&gt;&lt;/script&gt;</pre>'),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            with self.subTest(
                f"Testing plain text to html conversion for {s}...",
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(plain_text=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)

                # Stub out fake output from do_resolve_citations(), since the
                # purpose of this test is not to test that. We just need
                # something that looks like what create_cited_html() expects
                # to receive.
                citation_resolutions = {NO_MATCH_RESOURCE: citations}

                created_html = create_cited_html(opinion, citation_resolutions)
                self.assertEqual(
                    created_html,
                    expected_html,
                    msg=f"\n{created_html}\n\n    !=\n\n{expected_html}",
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
             '</span></i> Gerry of Massachusetts like</p></div>'),
        ]

        # fmt: on
        for s, expected_html in test_pairs:
            with self.subTest(
                f"Testing html to html conversion for {s}...",
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(html=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)

                # Stub out fake output from do_resolve_citations(), since the
                # purpose of this test is not to test that. We just need
                # something that looks like what create_cited_html() expects
                # to receive.
                citation_resolutions = {NO_MATCH_RESOURCE: citations}

                created_html = create_cited_html(opinion, citation_resolutions)
                self.assertEqual(
                    created_html,
                    expected_html,
                    msg=f"\n{created_html}\n\n    !=\n\n{expected_html}",
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
                f"Testing object to HTML rendering for {s}...",
                s=s,
                expected_html=expected_html,
            ):
                opinion = Opinion(plain_text=s)
                get_and_clean_opinion_text(opinion)
                citations = get_citations(opinion.cleaned_text)

                # Stub out fake output from do_resolve_citations(), since the
                # purpose of this test is not to test that. We just need
                # something that looks like what create_cited_html() expects
                # to receive. Also make sure that the "matched" opinion is
                # mocked appropriately.
                opinion.pk = "MATCH_ID"
                opinion.cluster = Mock(OpinionCluster(id=24601))
                opinion.cluster.get_absolute_url.return_value = "MATCH_URL"
                citation_resolutions = {opinion: citations}

                created_html = create_cited_html(opinion, citation_resolutions)

                self.assertEqual(
                    created_html,
                    expected_html,
                    msg=f"\n{created_html}\n\n    !=\n\n{expected_html}",
                )


class RECAPDocumentObjectTest(IndexedSolrTestCase):
    # pass
    @classmethod
    def setUpTestData(cls):
        cls.recap_doc = RECAPDocumentFactory.create(
            plain_text="In Fisher v. SD Protection Inc., 948 F.3d 593 (2d Cir. 2020), the Second Circuit held that in the context of settlement of FLSA and NYLL cases, which must be approved by the trial court in accordance with Cheeks v. Freeport Pancake House, Inc., 796 F.3d 199 (2d Cir. 2015), the district court abused its discretion in limiting the amount of recoverable fees to a percentage of the recovery by the successful plaintiffs. But also: sdjnfdsjnk. Fisher, 948 F.3d at 597.",
            ocr_status=RECAPDocument.OCR_UNNECESSARY,
            docket_entry=DocketEntryWithParentsFactory(),
        )
        # Courts
        court_ca2 = CourtFactory(id="ca2")

        # Citation 1
        cls.citation1 = CitationWithParentsFactory.create(
            volume="948",
            reporter="F.3d",
            page="593",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=court_ca2),
                case_name="Fisher v. SD Protection Inc.",
                date_filed=date(2020, 1, 1),
            ),
        )

        # Citation 2
        cls.citation2 = CitationWithParentsFactory.create(
            volume="796",
            reporter="F.3d",
            page="199",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=court_ca2),
                case_name="Cheeks v. Freeport Pancake House, Inc.",
                date_filed=date(2015, 1, 1),
            ),
        )

        super().setUpTestData()

    def test_opinionscited_recap_creation(self):
        """
        Tests that OpinionsCitedByRECAPDocument objects are created in the database,
        with correct citation counts.
        """
        test_recap_document = self.recap_doc

        store_recap_citations(test_recap_document)

        opinion1 = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
        opinion2 = Opinion.objects.get(cluster__pk=self.citation2.cluster_id)

        citation_test_pairs = [
            (opinion1, 2),
            (opinion2, 1),
        ]

        for cited_op, depth in citation_test_pairs:
            with self.subTest(
                f"Testing OpinionsCitedByRECAPDocument creation for {cited_op}...",
                cited=cited_op,
                depth=depth,
            ):
                citation_obj = OpinionsCitedByRECAPDocument.objects.get(
                    citing_document=test_recap_document, cited_opinion=cited_op
                )
                self.assertEqual(citation_obj.depth, depth)


class CitationObjectTest(ESIndexTestCase, TestCase):
    fixtures: List = []

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rebuild_index("search.OpinionCluster")
        super().setUpTestData()
        # Courts
        cls.court_scotus = CourtFactory(id="scotus")
        court_ca1 = CourtFactory(id="ca1")

        # Citation 1
        cls.citation1 = CitationWithParentsFactory.create(
            volume="1",
            reporter="U.S.",
            page="1",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=cls.court_scotus),
                case_name="Foo v. Bar",
                date_filed=date(
                    2000, 1, 1
                ),  # Year must equal text in citation4
            ),
        )

        # Citation 2
        cls.citation2 = CitationWithParentsFactory.create(
            volume="2",
            reporter="F.3d",
            page="2",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=court_ca1),
                case_name="Qwerty v. Uiop",
                date_filed=date(2000, 1, 1),  # F.3d must be after 1993
            ),
        )
        cls.citation2a = CitationWithParentsFactory.create(  # Extra citation for same OpinionCluster as above
            volume="9",
            reporter="F",
            page="1",
            cluster=OpinionCluster.objects.get(pk=cls.citation2.cluster_id),
        )

        # Citation 3
        cls.citation3 = CitationWithParentsFactory.create(
            volume="1",
            reporter="U.S.",
            page="50",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=cls.court_scotus),
                case_name="Lorem v. Ipsum",
            ),
        )

        # Citation 4
        cls.citation4 = CitationWithParentsFactory.create(
            volume="1",
            reporter="U.S.",
            page="999",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=cls.court_scotus),
                case_name="Abcdef v. Ipsum",
                sub_opinions=RelatedFactory(
                    OpinionWithChildrenFactory,
                    factory_related_name="cluster",
                    plain_text="Blah blah Foo v. Bar, 1 U.S. 1, 4, 2 S.Ct. 2, 5 (2000) (holding something happened that was at least five words)",
                ),
            ),
        )

        # Citation 5
        cls.citation5 = CitationWithParentsFactory.create(
            volume="123",
            reporter="U.S.",
            page="123",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=cls.court_scotus),
                case_name="Bush v. Gore",
                date_filed=date.today(),  # Must be later than any cited opinion
                sub_opinions=RelatedFactory(
                    OpinionWithChildrenFactory,
                    factory_related_name="cluster",
                    plain_text="America v. Maxwell, Bush v. John, Blah blah Foo v. Bar 1 U.S. 1, 77 blah blah. Asdf asdf Qwerty v. Uiop 2 F.3d 2, 555. Also check out Foo, 1 U.S. at 99 (holding that crime is illegal). Then let's cite Qwerty, supra, at 666 (noting that CourtListener is a great tool and everyone should use it). See also Foo, supra, at 101 as well. Another full citation is Lorem v. Ipsum 1 U. S. 50. Quoting Qwerty, “something something”, 2 F.3d 2, at 59. This case is similar to Fake, supra, and Qwerty supra, as well. This should resolve to the foregoing. Ibid. This should also convert appropriately, see Id., at 57. This should fail to resolve because the reporter and citation is ambiguous, 1 U. S., at 51. However, this should succeed, Lorem, 1 U.S., at 52.",
                ),
            ),
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def test_case_name_and_reverse_match_query(self) -> None:
        """Test refining match by case_name_query and reverse_match if full
        citations results are > 1
        """
        # Create 3 citations that match full_citation
        for i in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                citation = CitationWithParentsFactory.create(
                    volume="3",
                    reporter="U.S.",
                    page="888",
                    cluster=OpinionClusterFactoryWithChildrenAndParents(
                        docket=DocketFactory(court=self.court_scotus),
                        case_name="Obama v. Clinton",
                        date_filed=date.today(),
                        # Must be later than any cited opinion
                        sub_opinions=RelatedFactory(
                            OpinionWithChildrenFactory,
                            factory_related_name="cluster",
                            plain_text="Blah blah Foo v. Bar 1 U.S. 1, 77 blah blah.",
                        ),
                    ),
                )

        # Create the expected match Citation.
        with self.captureOnCommitCallbacks(execute=True):
            match_citation = CitationWithParentsFactory.create(
                volume="3",
                reporter="U.S.",
                page="888",
                cluster=OpinionClusterFactoryWithChildrenAndParents(
                    docket=DocketFactory(court=self.court_scotus),
                    case_name="America v. Maxwell",
                    date_filed=date.today(),
                    # Must be later than any cited opinion
                    sub_opinions=RelatedFactory(
                        OpinionWithChildrenFactory,
                        factory_related_name="cluster",
                        plain_text="Blah blah Foo v. Bar 1 U.S. 1, 77 blah blah.",
                    ),
                ),
            )

        full_citation = case_citation(
            volume="3",
            reporter="U.S.",
            page="888",
            index=1,
            reporter_found="U.S.",
            metadata={
                "court": "scotus",
                "defendant": "Maxwell",
                "plaintiff": "Brown",
            },
        )
        citing_opinion = Opinion.objects.get(
            cluster__pk=self.citation5.cluster_id
        )
        match_opinion = Opinion.objects.get(
            cluster__pk=match_citation.cluster_id
        )

        # Compare expected_resolutions.
        citation_resolutions = do_resolve_citations(
            [full_citation], citing_opinion
        )
        expected_resolutions = {match_opinion: [full_citation]}
        self.assertEqual(
            citation_resolutions,
            expected_resolutions,
            msg=f"\n{citation_resolutions}\n\n    !=\n\n{expected_resolutions}",
        )

    def test_citation_resolution(self) -> None:
        """Tests whether different types of citations (i.e., full, short form,
        supra, id) resolve correctly to opinion matches.
        """
        opinion1 = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
        opinion2 = Opinion.objects.get(cluster__pk=self.citation2.cluster_id)
        opinion3 = Opinion.objects.get(cluster__pk=self.citation3.cluster_id)
        opinion4 = Opinion.objects.get(cluster__pk=self.citation4.cluster_id)
        opinion5 = Opinion.objects.get(cluster__pk=self.citation5.cluster_id)

        full1 = case_citation(
            volume="1",
            reporter="U.S.",
            page="1",
            index=1,
            reporter_found="U.S.",
            metadata={"court": "scotus"},
        )
        full2 = case_citation(
            volume="2",
            reporter="F.3d",
            page="2",
            index=1,
            reporter_found="F.3d",
            metadata={"court": "ca1"},
        )
        full3 = case_citation(
            volume="1",
            reporter="U.S.",
            page="50",
            index=1,
            reporter_found="U.S.",
            metadata={"court": "scotus"},
        )
        full4 = case_citation(
            volume="1",
            reporter="U.S.",
            page="999",
            index=1,
            reporter_found="U.S.",
            metadata={"court": "scotus"},
        )
        full_na = case_citation(
            volume="1",
            reporter="U.S.",
            page="99",
            index=1,
            reporter_found="U.S.",
            metadata={"court": "scotus"},
        )

        supra1 = supra_citation(
            index=1,
            metadata={
                "antecedent_guess": "Bar",
                "pin_cite": "99",
                "volume": "1",
            },
        )
        supra3_or_4 = supra_citation(
            index=1,
            metadata={
                "antecedent_guess": "Ipsum",
                "pin_cite": "99",
                "volume": "1",
            },
        )

        short1 = case_citation(
            reporter="U.S.",
            page="99",
            volume="1",
            index=1,
            short=True,
            metadata={"antecedent_guess": "Bar,"},
        )
        short1_or_3_tiebreaker = case_citation(
            reporter="U.S.",
            page="99",
            volume="1",
            index=1,
            short=True,
            metadata={"antecedent_guess": "Bar"},
        )
        short1_or_3_bad_antecedent = case_citation(
            reporter="U.S.",
            page="99",
            volume="1",
            index=1,
            short=True,
            metadata={"antecedent_guess": "somethingwrong"},
        )
        short3_or_4_common_antecedent = case_citation(
            reporter="U.S.",
            page="99",
            volume="1",
            index=1,
            short=True,
            metadata={"antecedent_guess": "Ipsum"},
        )
        short_na = case_citation(
            reporter="F.3d",
            page="99",
            volume="1",
            index=1,
            short=True,
            metadata={"antecedent_guess": "somethingwrong"},
        )

        id = id_citation(index=1)
        non = nonopinion_citation(index=1, source_text="§99")
        journal = journal_citation(reporter="Minn. L. Rev.")
        law = law_citation(
            source_text="1 Stat. 2",
            reporter="Stat.",
            groups={"volume": "1", "page": "2"},
        )

        test_pairs = [
            # Simple test for matching a single, full citation
            ([full1], {opinion1: [full1]}),
            # Test matching multiple full citations to different documents
            ([full1, full2], {opinion1: [full1], opinion2: [full2]}),
            # Test matching an unmatchacble full citation
            ([full_na], {NO_MATCH_RESOURCE: [full_na]}),
            # Test resolving a supra citation
            ([full1, supra1], {opinion1: [full1, supra1]}),
            # Test resolving a supra citation when its antecedent guess matches
            # two possible candidates. We expect the supra citation to not
            # be matched.
            (
                [full3, full4, supra3_or_4],
                {opinion3: [full3], opinion4: [full4]},
            ),
            # Test resolving a supra citation when the previous citation
            # match failed.
            # We expect the supra citation to not be matched.
            ([full_na, supra1], {NO_MATCH_RESOURCE: [full_na]}),
            # Test resolving a short form citation with a meaningful antecedent
            ([full1, short1], {opinion1: [full1, short1]}),
            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates. We expect its antecedent
            # guess to provide the correct tiebreaker.
            (
                [full1, full3, short1_or_3_tiebreaker],
                {opinion1: [full1, short1_or_3_tiebreaker], opinion3: [full3]},
            ),
            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates, and when it lacks a
            # meaningful antecedent.
            # We expect the short form citation to not be matched.
            (
                [full1, full3, short1_or_3_bad_antecedent],
                {opinion1: [full1], opinion3: [full3]},
            ),
            # Test resolving a short form citation when its reporter and
            # volume match two possible candidates, and when its antecedent
            # guess also matches multiple possibilities.
            # We expect the short form citation to not be matched.
            (
                [full3, full4, short3_or_4_common_antecedent],
                {opinion3: [full3], opinion4: [full4]},
            ),
            # Test resolving a short form citation when its reporter and
            # volume are erroneous.
            # We expect the short form citation to not be matched.
            ([full1, short_na], {opinion1: [full1]}),
            # Test resolving a short form citation when the previous citation
            # match failed.
            # We expect the short form citation to not be matched.
            ([full_na, short1], {NO_MATCH_RESOURCE: [full_na]}),
            # Test resolving an Id. citation
            ([full1, id], {opinion1: [full1, id]}),
            # Test resolving an Id. citation when the previous citation match
            # failed because there is no clear antecedent. We expect the Id.
            # citation to also not be matched.
            (
                [full1, short_na, id],
                {opinion1: [full1]},
            ),
            # Test resolving an Id. citation when the previous citation match
            # failed because a normal full citation lookup returned nothing.
            # We expect the Id. citation to be matched to the
            # NO_MATCH_RESOURCE placeholder object.
            (
                [full1, full_na, id],
                {opinion1: [full1], NO_MATCH_RESOURCE: [full_na, id]},
            ),
            # Test resolving an Id. citation when the previous citation is to a
            # non-opinion document. Since we can't match those documents (yet),
            # we expect the Id. citation to also not be matched.
            (
                [full1, non, id],
                {opinion1: [full1]},
            ),
            # Test resolving an Id. citation when it is the first citation
            # found. Since there is nothing before it, we expect no matches to
            # be returned.
            ([id], {}),
            # Test resolving a law citation. Since we don't support these yet,
            # we expect no matches to be returned.
            ([law], {NO_MATCH_RESOURCE: [law]}),
            # Test resolving a journal citation. Since we don't support these
            # yet, we expect no matches to be returned.
            ([journal], {NO_MATCH_RESOURCE: [journal]}),
        ]

        # fmt: on
        for citations, expected_resolutions in test_pairs:
            with self.subTest(
                f"Testing citation matching for {citations}...",
                citations=citations,
                expected_resolutions=expected_resolutions,
            ):
                # The citing opinion must contain the name of the cited case
                # if a reverse_match() call is required
                citing_opinion = opinion5

                citation_resolutions = do_resolve_citations(
                    citations, citing_opinion
                )
                self.assertEqual(
                    citation_resolutions,
                    expected_resolutions,
                    msg=f"\n{citation_resolutions}\n\n    !=\n\n{expected_resolutions}",
                )

    def test_citation_matching_issue621(self) -> None:
        """Make sure that a citation like 1 Wheat 9 doesn't match 9 Wheat 1"""
        # citation2a is 9 F. 1, so we expect no results.
        citation_str = "1 F. 9 (1795)"
        citation = get_citations(citation_str)[0]
        results = resolve_fullcase_citation(citation)
        self.assertEqual(NO_MATCH_RESOURCE, results)

    def test_citation_increment(self) -> None:
        """Make sure that found citations update the increment on the cited
        opinion's citation count"""
        opinion1 = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
        opinion5 = Opinion.objects.get(cluster__pk=self.citation5.cluster_id)

        # Updates cited opinion's citation count in a Celery task
        find_citations_and_parentheticals_for_opinion_by_pks.delay(
            [opinion5.pk]
        )

        cited = Opinion.objects.get(pk=opinion1.pk)
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
        # Here, opinion5 is our mock citing opinion, containing a number of references
        # to other mocked opinions, mixed about. It's hard to exhaustively
        # test all combinations, but this test case is made to be deliberately
        # complex, in an effort to "trick" the algorithm. Cited opinions:
        # opinion1: 1 FullCaseCitation, 1 ShortCaseCitation, 1 SupraCitation (depth=3)
        # (case name Foo)
        # opinion2: 1 FullCaseCitation, 2 IdCitation (one Id. and one Ibid.),
        #   1 ShortCaseCitation, 2 SupraCitation (depth=6) (case name Qwerty)
        # opinion3: 1 FullCaseCitation, 1 ShortCaseCitation (depth=2) (case name Lorem)
        opinion1 = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
        opinion2 = Opinion.objects.get(cluster__pk=self.citation2.cluster_id)
        opinion3 = Opinion.objects.get(cluster__pk=self.citation3.cluster_id)
        opinion5 = Opinion.objects.get(cluster__pk=self.citation5.cluster_id)

        citing = opinion5
        find_citations_and_parentheticals_for_opinion_by_pks.delay(
            [opinion5.pk]
        )

        citation_test_pairs = [
            (opinion1, 3),
            (opinion2, 6),
            (opinion3, 2),
        ]

        for cited, depth in citation_test_pairs:
            with self.subTest(
                f"Testing OpinionsCited creation for {cited}...",
                cited=cited,
                depth=depth,
            ):
                self.assertEqual(
                    OpinionsCited.objects.get(
                        citing_opinion=citing, cited_opinion=cited
                    ).depth,
                    depth,
                )

        description_test_pairs = [
            (opinion1, 1),
            (opinion2, 1),
            (opinion3, 0),
        ]
        for described, num_parentheticals in description_test_pairs:
            with self.subTest(
                f"Testing Parenthetical and ParentheticalGroup creation for {described}...",
                described=described,
                num_descriptions=num_parentheticals,
            ):
                self.assertEqual(
                    Parenthetical.objects.filter(
                        describing_opinion=citing, described_opinion=described
                    ).count(),
                    num_parentheticals,
                )
                # Make sure at least one ParentheticalGroup is created if
                # there is at least one parenthetical
                if num_parentheticals > 0:
                    self.assertGreaterEqual(
                        ParentheticalGroup.objects.filter(
                            opinion=described
                        ).count(),
                        1,
                    )

    def test_no_duplicate_parentheticals_from_parallel_cites(self) -> None:
        citing = Opinion.objects.get(cluster__pk=self.citation4.cluster_id)
        cited = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
        find_citations_and_parentheticals_for_opinion_by_pks.delay([citing.pk])
        self.assertEqual(
            Parenthetical.objects.filter(
                describing_opinion=citing, described_opinion=cited
            ).count(),
            1,
        )


class CitationFeedTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.rebuild_index("search.OpinionCluster")
        super().setUpTestData()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def _tree_has_content(self, content, expected_count):
        xml_tree = etree.fromstring(content)
        count = len(
            xml_tree.xpath(
                "//a:entry", namespaces={"a": "http://www.w3.org/2005/Atom"}
            )
        )
        self.assertEqual(count, expected_count)

    async def test_basic_cited_by_feed(self) -> None:
        """Can we load the cited-by feed and does it have content?"""
        r = await self.async_client.get(
            reverse("search_feed", args=["search"]),
            {"q": f"cites:{self.opinion_1.pk}"},
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)

    async def test_unicode_content(self) -> None:
        """Does the citation feed continue working even when we have a unicode
        case name?
        """
        new_case_name = (
            "MAC ARTHUR KAMMUELLER, \u2014 v. LOOMIS, FARGO & " "CO., \u2014"
        )
        await OpinionCluster.objects.filter(
            pk=self.opinion_cluster_1.pk
        ).aupdate(case_name=new_case_name)

        r = await self.async_client.get(
            reverse("search_feed", args=["search"]),
            {"q": f"cites:{self.opinion_1.pk}"},
        )
        self.assertEqual(r.status_code, 200)

        expected_count = 1
        self._tree_has_content(r.content, expected_count)


class CitationCommandTest(IndexedSolrTestCase):
    """Test a variety of the ways that find_citations can be called."""

    fixtures: List = []

    @classmethod
    def setUpTestData(cls) -> None:
        # Court
        court_scotus = CourtFactory(id="scotus")

        # Citation 1 - cited opinion
        cls.citation1 = CitationWithParentsFactory.create(
            volume="1",
            reporter="Yeates",
            page="1",
        )

        # Citation 2 - citing opinion
        cls.citation2 = CitationWithParentsFactory.create(
            volume="56",
            reporter="F.2d",
            page="9",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=court_scotus),
                case_name="Foo v. Bar",
                date_filed=date.today(),  # Must be later than any cited opinion
                sub_opinions=RelatedFactory(
                    OpinionWithChildrenFactory,
                    factory_related_name="cluster",
                    plain_text="Blah blah 1 Yeates 1",
                ),
            ),
        )

        # Citation 3
        cls.citation3 = CitationWithParentsFactory.create(
            volume="56",
            reporter="F.2d",
            page="11",
        )

        # Opinions IDs
        cls.opinion_id2 = Opinion.objects.get(
            cluster__pk=cls.citation2.cluster_id
        ).pk
        cls.opinion_id3 = Opinion.objects.get(
            cluster__pk=cls.citation3.cluster_id
        ).pk

    def call_command_and_test_it(self, args):
        call_command("find_citations", *args)
        cited = Opinion.objects.get(cluster__pk=self.citation1.cluster_id)
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
            f"{self.opinion_id2}",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_doc_ids(self) -> None:
        args = [
            "--doc-id",
            f"{self.opinion_id3}",
            f"{self.opinion_id2}",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_only(self) -> None:
        args = [
            "--start-id",
            f"{min(self.opinion_id2, self.opinion_id3)}",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_index_by_start_and_end(self) -> None:
        args = [
            "--start-id",
            f"{min(self.opinion_id2, self.opinion_id3)}",
            "--end-id",
            f"{max(self.opinion_id2, self.opinion_id3)}",
            "--index",
            "concurrently",
        ]
        self.call_command_and_test_it(args)

    def test_filed_after(self) -> None:
        args = [
            "--filed-after",
            f"{OpinionCluster.objects.get(pk=self.citation2.cluster_id).date_filed - timedelta(days=1)}",
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
                f"Testing parallel citation identification for: {q}...",
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
                f"Testing network-friendly edge creation for: {q}...",
                q=q,
                a=a,
            ):
                self.assertEqual(make_edge_list(q), a)


class FilterParentheticalTest(SimpleTestCase):
    def test_is_not_descriptive(self):
        fixtures = [
            "Gonzales II",
            "Third Circuit 2013",
            "3d. Cir. 1776",
            "emphasis in original",
            "quotation altered",
            "internal citations and quotations omitted",
            "citations and internal ellipses omitted",
            "quotation marks omitted; ellipses ours",
            "headings and internal quotations omitted, emphasis and citations altered",
            "plurality opinion",
            "opinion of Breyer, J.",
            "opinion of Mister Justice Black",
            "supplemental opinion",
            "majority continuance in part",
            "dicta",
            "denying cert",
            "denying certiorari",
            "as amended",
            "contra",
            "authority below",
            "statement below",
            "citing Raich v. Conzales, 123 F.3d 123 (2019)",
            "third circuit",
            "hereinafter, this rules applies.",
            "Scalia, J., concurring in the judgment",
            "Sotomayor, J., statement respecting denial of certiorari",
            "Roberts, C.J., concurring in part and dissenting in part",
            "Friendly, J., concurring in the judgment, concurring in part, and dissenting in part",
            "Scalia, J., specially concurring in the judgment on this issue",
            "en banc",
            "per curiam",
            "same",
            "standard of review",
            "opinion of O'Connor, J., respecting the granting of an injunction",
            "no",
            "n. 3",
            "No. 12-345",
            "TILA",
            "citing Jones",
            "cited in Heart of Atlanta Motel v. United States",
            "quoting Hart Steel Co. v. Railroad Supply Co., 244 U.S. 294, 299, 37 S. Ct. 506, 508, 61 L. Ed. 1148 (1917)",
            "collecting cases",
            "holding that too short",
            "First Amendment",
            "mislabeled product",
            "Section 403(d)(2)",
        ]
        for i, parenthetical_text in enumerate(fixtures):
            with self.subTest(
                f"Testing {parenthetical_text} is not descriptive...", i=i
            ):
                self.assertFalse(
                    is_parenthetical_descriptive(parenthetical_text),
                    f"Got incorrect result from is_parenthetical_descriptive for text (expected False): {parenthetical_text}",
                )

    def test_is_descriptive(self):
        fixtures = [
            "holding that 2 + 2 = 5",
            "accountant who gave lay opinion testimony might have qualified as expert",
            "where plaintif's complaint alleges facts which, if proven, would entitle plaintiff to relief under the Eighth Amendment, dismissal of complaint was inappropriate",
            "ruling that there is nothing either legal or illegal, only thinking makes it so",
            "testing that the mere presence of the word quotation doesn't get a parenthetical filtered out if it's long enough",
            '"Look on my Works, ye Mighty, and despair"',
            '"Texas does not seek to have the Court interpret the Constitution, so much as disregard it."',
            "questioning whether he who made the Lamb made thee",
            "holding that just long enough",
        ]

        for i, parenthetical_text in enumerate(fixtures):
            with self.subTest(
                f"Testing {parenthetical_text} is descriptive...", i=i
            ):
                self.assertTrue(
                    is_parenthetical_descriptive(parenthetical_text),
                    f"Got incorrect result from is_parenthetical_descriptive for text (expected True): {parenthetical_text}",
                )

    def test_clean_text(self):
        test_pairs = [
            (
                "This parenthetical is as it should be",
                "This parenthetical is as it should be",
            ),
            (
                "Does not remove part of a reporter citation. See Hurley, 583 U.S. ---",
                "Does not remove part of a reporter citation. See Hurley, 583 U.S. ---",
            ),
            (
                "Gets rid of ------- divider characters properly",
                "Gets rid of divider characters properly",
            ),
            (
                "Replaces    \n extra whitespace\r\r\r\r with a single space",
                "Replaces extra whitespace with a single space",
            ),
            (
                "Removes *389 star pagination * 456 marks in the text",
                "Removes star pagination marks in the text",
            ),
            (
                "Deals properly *123 with a mix of ---- \r\n \n ------ different issues",
                "Deals properly with a mix of different issues",
            ),
        ]

        for i, (input_text, expected_clean_text) in enumerate(test_pairs):
            with self.subTest(
                f"Testing description text cleaning for {input_text}...", i=i
            ):
                self.assertEqual(
                    clean_parenthetical_text(input_text),
                    expected_clean_text,
                    f"Got incorrect result from clean_parenthetical_text for text: {input_text}",
                )


DescriptionUtilityTestCase = Tuple[Tuple[str, int], Tuple[str, int], int]


class DescriptionScoreTest(SimpleTestCase):
    def test_description_score_h2h(self) -> None:
        """
        Tests the functionality of the description utility metric by comparing
        its accuracy at picking the better of two descriptions (as determined
        by a human)
        """
        minimum_accuracy = 0.9
        test_cases: List[DescriptionUtilityTestCase] = [
            (
                (
                    "holding that a State may not require a parade to include a group if the parade's organizer disagrees with the group's message",
                    110,
                ),
                (
                    "state law cannot require a parade to include a group whose message the parade's organizer does not wish to send",
                    1043,
                ),
                0,
            ),
            (
                (
                    "ruling that failure to Mirandize a witness before his confession automatically results in exclusion of the statement's use in the prosecution's case in chief",
                    15,
                ),
                (
                    'holding that statements obtained in violation of Miranda are irrebuttably presumed involuntary "for purposes of the prosecution\'s case in chief"',
                    603,
                ),
                1,
            ),
            (
                (
                    'holding that pursuant to the trial judge\'s "gatekeeping responsibility," she "must ensure that any and all scientific testimony or evidence admitted is not only relevant, but reliable"',
                    28,
                ),
                (
                    "overruling Frye",
                    48,
                ),
                0,
            ),
            (
                (
                    'discussing the legislative history to the 1986 amendments as demonstrating a congressional intent to encourage qui tam suits brought "by insiders, such as employees who come across information of fraud in the course of their employment"',
                    58,
                ),
                (
                    "detailing the history of the FCA",
                    93,
                ),
                0,
            ),
            (
                (
                    "focusing upon interstate effects",
                    45,
                ),
                (
                    "specific statutory provisions overcome inferences to contrary from general, ambiguous legislative declarations",
                    49,
                ),
                1,
            ),
            (
                (
                    "Like other sanctions, attorney's fees should not be assessed lightly or without fair notice and an opportunity for a hearing on the record",
                    18,
                ),
                (
                    "inherent power of court",
                    49,
                ),
                0,
            ),
            (
                (
                    'determining that error is not harmless if court "is left in grave doubt"',
                    9,
                ),
                (
                    'concluding that error had sufficient influence if court "is left in grave doubt"',
                    1500,
                ),
                1,
            ),
            (
                (
                    "construing Title III's requirements that the government identify probable wiretap subjects and that it give subsequent notice to those whose conversations were intercepted",
                    33,
                ),
                (
                    '"It is not a constitutional requirement that all those likely to be overheard engaging in incriminating conversations be named."',
                    472,
                ),
                0,
            ),
            (
                (
                    'holding that a defendant\'s "desire to exchange one mandatory counsel for another . . . does not signify that he was abandoning his Sixth Amendment right to have none"',
                    94,
                ),
                (
                    "right is unqualified if request made before start of trial",
                    99,
                ),
                0,
            ),
            (
                (
                    '"New York has no power to project its legislation into Vermont by regulating the price to be paid in that state for milk acquired there."',
                    956,
                ),
                (
                    'declaring that "one state in its dealings with another may not place itself in a position of economic isolation"',
                    13,
                ),
                1,
            ),
        ]
        num_correct = 0
        failed_cases = []
        for desc_a, desc_b, correct_idx in test_cases:
            score_a, score_b = (
                parenthetical_score(
                    desc[0], OpinionCluster(citation_count=desc[1])
                )
                for desc in (desc_a, desc_b)
            )
            higher_score_idx = 0 if score_a >= score_b else 1
            if higher_score_idx == correct_idx:
                num_correct += 1
            else:
                failed_cases.append((desc_a, desc_b, correct_idx))
        actual_accuracy = num_correct / len(test_cases)
        self.assertGreaterEqual(
            actual_accuracy,
            minimum_accuracy,
            f"Description score head-to-head test failed because the accuracy was below the required threshold. Failed test cases: {self._print_failed_cases(failed_cases)}",
        )

    def test_handles_zero_citation_count(self):
        # Just a basic smoke test to ensure it doesn't blow up when the citation count is 0
        cluster = OpinionCluster(citation_count=0)
        result = parenthetical_score(
            "some parenthetical, it's not important what", cluster
        )
        self.assertGreater(result, 0)

    def _print_failed_cases(
        self, failed_cases: List[DescriptionUtilityTestCase]
    ) -> str:
        output = ""
        for case in failed_cases:
            output += f"\nDescription 0: {case[0]}\nDescription 1: {case[1]}\nExpected Winner: {case[2]}\n"
        return output


@dataclass(frozen=True)
class DummyParenthetical:
    """
    A simple dummy version of the Parenthetical class that doesn't require
    describing_opinion and described_opinion, and is hashable. It is useful for
    testing GroupParenthetical functionality
    """

    id: int
    text: str
    score: float

    def __hash__(self):
        return self.id

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return str(self.id)


class GroupParentheticalsTest(SimpleTestCase):
    def test_get_parenthetical_groups(self):
        """
        Test whether get_parenthetical_groups correctly sub-divides a given
        list of parentheticals into clusters of parentheticals that are
        textually similar to each other.
        """
        expected_groups = [
            (
                [
                    DummyParenthetical(
                        text='Holding that inmate must establish actual injury, rather than "theoretical deficiency" with legal library or legal assistance program to state constitutional claim for interference with access to courts',
                        id=0,
                        score=0,
                    ),
                    DummyParenthetical(
                        text="Holding that a prisoner must show an actual injury to state a claim for denial of access to courts",
                        id=1,
                        score=0,
                    ),
                ],
                [
                    DummyParenthetical(
                        text="Holding further that the legal claim affected must be one that either directly or collaterally attacks plaintiff’s conviction or sentence, or one that challenges the conditions of his confinement",
                        id=2,
                        score=0,
                    )
                ],
            ),
            (
                [
                    DummyParenthetical(
                        text="Reiterating that the Excessive Fines Clause has its 13 roots in the Magna Carta, which “required that economic sanctions ‘be proportioned to the wrong’ and ‘not be so large as to deprive [an offender] of his livelihood’”",
                        id=3,
                        score=0,
                    )
                ],
            ),
            (
                [
                    DummyParenthetical(
                        text='Finding that forfeitures are fines "if they constitute punishment for an offense"',
                        id=4,
                        score=0,
                    ),
                ],
                [
                    DummyParenthetical(
                        text="Despite differing facts emphasized by the majority and dissent, the majority held that “Respondent’s crime was solely a reporting offense”",
                        id=5,
                        score=0,
                    ),
                ],
                [
                    DummyParenthetical(
                        text="“[D]espite the differences between restitution and a traditional fine, restitution still implicates the prosecutorial powers of government[.]”",
                        id=6,
                        score=0,
                    ),
                ],
            ),
            (
                [
                    DummyParenthetical(
                        text="Finding valid a federal law criminalizing the destruction or mutilation of a draft registration against a First Amendment challenge",
                        id=10,
                        score=0,
                    ),
                ],
                [
                    DummyParenthetical(
                        text="Applying medium scrutiny test to state action having an incidental effect on right to free expression ",
                        id=11,
                        score=0,
                    )
                ],
            ),
            (
                [
                    DummyParenthetical(
                        text="The loss of First Amendment freedoms, for even minimal period of time, unquestionably constitutes irreparable injury.",
                        id=11,
                        score=0,
                    ),
                    DummyParenthetical(
                        text="The loss of First Amendment freedoms, for even minimal period of time, unquestionably constitutes irreparable injury.",
                        id=12,
                        score=0,
                    ),
                    DummyParenthetical(
                        text="The loss of First Amendment freedoms, for even minimal period of time, unquestionably constitutes irreparable injury.",
                        id=13,
                        score=0,
                    ),
                ],
                [
                    DummyParenthetical(
                        text=" Holding public employees could not be fired because of their politics unless they held “policymaking” or “confidential” positions ",
                        id=14,
                        score=0,
                    ),
                ],
            ),
        ]
        for i, groups in enumerate(expected_groups):
            with self.subTest(f"Testing {groups} are grouped correctly.", i=i):
                # `groups` has the parentheticals divided into the correct groups.
                # We flatten it into a single list and see if the algorithm
                # comes up with the same groupings when we pass it the flat list
                flat = list(itertools.chain.from_iterable(groups))
                output_groups = compute_parenthetical_groups(flat)
                output_sets = frozenset(
                    [frozenset(pg.parentheticals) for pg in output_groups]
                )
                input_sets = frozenset([frozenset(g) for g in groups])
                self.assertEqual(
                    input_sets,
                    output_sets,
                    f"Got incorrect result from get_parenthetical_groups for: {groups}",
                )

    def test_get_representative_parenthetical(self):
        """
        Tests whether get_representative parenthetical identifies the correct
        parenthetical as the most representative of the given list of
        parentheticals based on its similarity to others and descriptiveness
        score.
        """
        simgraph = {
            "0": ["3"],
            "1": ["2", "3", "7"],
            "2": ["1"],
            "3": ["0", "1"],
            "4": ["5"],
            "5": ["4"],
            "6": [],
            "7": ["1"],
        }

        parentheticals = [
            DummyParenthetical(id=0, text="par0", score=1),
            DummyParenthetical(id=1, text="par1", score=1),
            DummyParenthetical(id=2, text="par2", score=1),
            DummyParenthetical(id=3, text="par3", score=1),
            DummyParenthetical(id=4, text="par4", score=1),
            DummyParenthetical(id=5, text="par5", score=1),
            DummyParenthetical(id=6, text="par6", score=1),
            DummyParenthetical(id=7, text="par7", score=1),
        ]
        # Test pair format:
        # (
        #   (list of parentheticals to find the most representative one from, similarity graph),
        #   correct representative parenthetical
        #  )
        test_pairs = [
            ((parentheticals[0:3], simgraph), parentheticals[0]),
            ((parentheticals[0:6], simgraph), parentheticals[1]),
            ((parentheticals[0:1], simgraph), parentheticals[0]),
            ((parentheticals[7:], simgraph), parentheticals[7]),
        ]

        for i, (
            (parentheticals_to_test, simgraph_to_test),
            representative,
        ) in enumerate(test_pairs):
            with self.subTest(
                "Testing that representative connected parenthetical is selected correctly.",
                i=i,
            ):
                self.assertEqual(
                    get_representative_parenthetical(
                        parentheticals_to_test, simgraph_to_test
                    ),
                    representative,
                    f"Got incorrect result from get_best_parenthetical_of_group for text (expected {representative}): {(parentheticals_to_test, simgraph_to_test)}",
                )

    def test_get_parenthetical_tokens(self):
        """
        Tests whether get_parenthetical_tokens correctly converts the text of a
        parenthetical to a list of tokens
        """
        test_pairs = [
            (
                "Concluding that a TDCA claim failed because the plaintiffs always knew the answers to those questions",
                [
                    "tdca",
                    "claim",
                    "fail",
                    "plaintiff",
                    "alway",
                    "knew",
                    "answer",
                    "question",
                ],
            ),
            (
                "Holding that in ruling upon an RCFC 12(b)(6) motion, the Court must accept as true the undisputed factual allegations in the complaint",
                [
                    "rule",
                    "upon",
                    "rcfc",
                    "12b6",
                    "motion",
                    "court",
                    "must",
                    "accept",
                    "true",
                    "undisput",
                    "factual",
                    "alleg",
                    "complaint",
                ],
            ),
            ("", []),
        ]
        for i, (parenthetical_text, tokens) in enumerate(test_pairs):
            with self.subTest(
                f"Testing {parenthetical_text} is tokenized correctly.", i=i
            ):
                self.assertEqual(
                    get_parenthetical_tokens(parenthetical_text),
                    tokens,
                    f"Got incorrect result from get_parnethetical_tokens for text (expected {tokens}): {parenthetical_text}",
                )

    def test_get_graph_component(self):
        """
        Tests whether get_graph_component correctly identifies the full
        "connected component" of a given node in the graph (i.e. a list of
        itself plus any nodes directly or indirectly connected to it)
        """
        test_pairs = [
            (("1", {"1": []}, set()), ["1"]),
            (("1", {"1": ["2"], "2": "1", "3": []}, set()), ["1", "2"]),
            (
                (
                    "1",
                    {
                        "1": ["2", "3"],
                        "2": "1",
                        "3": ["1"],
                        "4": ["5"],
                        "5": ["4"],
                    },
                    set(),
                ),
                ["1", "2", "3"],
            ),
            (
                (
                    "2",
                    {
                        "1": ["2", "3"],
                        "2": "1",
                        "3": ["1"],
                        "4": ["5"],
                        "5": ["4"],
                    },
                    set(),
                ),
                ["1", "2", "3"],
            ),
            (
                (
                    "3",
                    {
                        "1": ["2", "3"],
                        "2": "1",
                        "3": ["1"],
                        "4": ["5"],
                        "5": ["4"],
                    },
                    set(),
                ),
                ["1", "2", "3"],
            ),
        ]
        for i, (inputs, output) in enumerate(test_pairs):
            with self.subTest(
                f"Testing {inputs} connections are recognized correctly.", i=i
            ):
                self.assertEqual(
                    sorted(get_graph_component(*inputs)),
                    sorted(output),
                    f"Got incorrect result from get_graph_component for inputs (expected {output}): {inputs}",
                )
