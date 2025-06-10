from django.db import models
from eyecite.models import FullCaseCitation

from cl.citations.utils import map_reporter_db_cite_type
from cl.search.models import BaseCitation, Citation, Opinion, RECAPDocument


class BaseUnmatchedCitation(BaseCitation):
    """
    Track citations that couldn't be resolved to a RecapDocument or
    OpinionCluster
    """

    NO_CITATION = 1
    FOUND = 2
    RESOLVED = 3
    FAILED_AMBIGUOUS = 4
    FAILED = 5
    STATUS = (
        (
            NO_CITATION,
            "The citation does not exist in the search_citation table.",
        ),
        (
            FOUND,
            "The citation now exists on the search_citation table. "
            "In the case of opinions, we haven't tried to update the citing "
            "Opinion.html_with_citations yet",
        ),
        (
            RESOLVED,
            "The citation resolution task was run successfully and this "
            "citation is now matched. In the case of opinions, citing "
            "Opinion.html_with_citations was updated successfully",
        ),
        (
            FAILED_AMBIGUOUS,
            "The citation resolution failed because this citation resolved to "
            "more than 1 cluster. In the case of opinions, the citing opinion "
            "Opinion.html_with_citations update failed for this citation.",
        ),
        (
            FAILED,
            "We couldn't resolve the citation. In the case of opinions, the "
            "citing Opinion.html_with_citations update failed for this "
            "citation",
        ),
    )
    status: models.SmallIntegerField = models.SmallIntegerField(
        help_text="Status of resolution of the initially unmatched citation",
        choices=STATUS,
    )
    citation_string: models.TextField = models.TextField(
        help_text="The unparsed citation string in case it doesn't match the "
        "regular citation model in BaseCitation"
    )
    court_id: models.TextField = models.TextField(
        help_text="A court_id as identified by eyecite from the opinion's "
        "context. May be useful to know where to find missing citations"
    )
    year: models.SmallIntegerField = models.SmallIntegerField(
        help_text="A year identified by eyecite from the opinion's context",
        null=True,
    )

    class Meta:
        abstract = True

    @classmethod
    def create_from_eyecite_base(
        cls,
        eyecite_citation: FullCaseCitation,
        has_multiple_matches: bool,
    ):
        """
        Create an UnmatchedCitation instance using an eyecite FullCaseCitation

        Saving is left to the caller

        :param eyecite_citation: a FullCaseCitation as returned by
            eyecite.get_citations
        :param has_multiple_matches: if the citation was resolved to
            MULTIPLE_MATCHES_RESOURCE
        :return: a UnmatchedCitation object, without a `citing_opinion` or
            `citing_recapdocument`
        """
        cite_type_str = eyecite_citation.all_editions[0].reporter.cite_type
        year = eyecite_citation.metadata.year
        unmatched_citation = cls(
            status=cls.NO_CITATION,
            citation_string=eyecite_citation.matched_text(),
            court_id=eyecite_citation.metadata.court or "",
            year=int(year) if year else None,
            volume=eyecite_citation.groups["volume"],
            reporter=eyecite_citation.corrected_reporter(),
            page=eyecite_citation.corrected_page(),
            type=map_reporter_db_cite_type(cite_type_str),
        )

        # The citation exists in the search_citation table, but it couldn't
        # be resolved
        if has_multiple_matches:
            unmatched_citation.status = cls.FAILED_AMBIGUOUS
        elif Citation.objects.filter(
            volume=unmatched_citation.volume,
            reporter=unmatched_citation.reporter,
            page=unmatched_citation.page,
            type=unmatched_citation.type,
        ).exists():
            unmatched_citation.status = cls.FAILED

        return unmatched_citation


class UnmatchedCitation(BaseUnmatchedCitation):
    citing_opinion: models.ForeignKey = models.ForeignKey(
        Opinion,
        help_text="The opinion citing this citation",
        on_delete=models.CASCADE,
        related_name="unmatched_citations",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["volume", "reporter", "page"],
            )
        ]
        #
        unique_together = (("citing_opinion", "volume", "reporter", "page"),)

    @classmethod
    def create_from_eyecite(
        cls,
        eyecite_citation: FullCaseCitation,
        citing_opinion: Opinion,
        has_multiple_matches: bool,
    ):
        """
        :param citing_document: the opinion that cited this unresolved citation

        """
        unmatched_citation = cls.create_from_eyecite_base(
            eyecite_citation, has_multiple_matches
        )
        unmatched_citation.citing_opinion = citing_opinion
        return unmatched_citation


class UnmatchedCitationFromRECAPDocument(BaseUnmatchedCitation):
    citing_recapdocument: models.ForeignKey = models.ForeignKey(
        RECAPDocument,
        help_text="The RECAPDocument citing this unmatched citation",
        on_delete=models.CASCADE,
        related_name="unmatched_citations",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["volume", "reporter", "page"],
            )
        ]
        #
        unique_together = (
            ("citing_recapdocument", "volume", "reporter", "page"),
        )

    @classmethod
    def create_from_eyecite(
        cls,
        eyecite_citation: FullCaseCitation,
        citing_recapdocument: RECAPDocument,
        has_multiple_matches: bool,
    ):
        """
        :param citing_document: the opinion that cited this unresolved citation

        """
        unmatched_citation = cls.create_from_eyecite_base(
            eyecite_citation, has_multiple_matches
        )
        unmatched_citation.citing_recapdocument = citing_recapdocument
        return unmatched_citation
