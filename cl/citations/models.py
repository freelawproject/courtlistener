from django.db import models
from eyecite.models import FullCaseCitation

from cl.citations.utils import map_reporter_db_cite_type
from cl.search.models import BaseCitation, Opinion


class UnmatchedCitation(BaseCitation):
    """Keep track of citations that could not be resolved to a cluster on the
    batch citator run
    """

    UNMATCHED = 1
    FOUND = 2
    RESOLVED = 3
    FAILED_AMBIGUOUS = 4
    FAILED = 5
    STATUS = (
        (
            UNMATCHED,
            "The citation does not exist in the search_citation table."
            " We couldn't match the citation to a cluster on the "
            " previous citation extractor run",
        ),
        (
            FOUND,
            "The citation exists on the search_citation table. We "
            " haven't updated the citing Opinion.html_with_citations yet",
        ),
        (
            RESOLVED,
            "The citing Opinion.html_with_citations was updated successfully",
        ),
        (
            FAILED_AMBIGUOUS,
            "The citing Opinion.html_with_citations update "
            "failed because the citation is ambiguous",
        ),
        (FAILED, "The citing Opinion.html_with_citations update failed"),
    )
    citing_opinion: models.ForeignKey = models.ForeignKey(
        Opinion,
        help_text="The opinion citing this citation",
        on_delete=models.CASCADE,
        related_name="eyecite_citations",
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
    year: models.TextField = models.TextField(
        help_text="A year identified by eyecite from the opinion's context"
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
        cls, eyecite_citation: FullCaseCitation, citing_opinion: Opinion
    ):
        """
        Create an UnmatchedCitation instance using an eyecite FullCaseCitation

        Saving is left to the caller

        :param eyecite_citation: a FullCaseCitation as returned by
            eyecite.get_citations
        :param citing_opinion: the opinion which uses the citation
        """
        cite_type_str = eyecite_citation.all_editions[0].reporter.cite_type
        return cls(
            citing_opinion=citing_opinion,
            status=cls.UNMATCHED,
            citation_string=eyecite_citation.matched_text(),
            court_id=eyecite_citation.metadata.court or "",
            year=eyecite_citation.metadata.year or "",
            volume=eyecite_citation.groups["volume"],
            reporter=eyecite_citation.corrected_reporter(),
            page=eyecite_citation.groups["page"],
            type=map_reporter_db_cite_type(cite_type_str),
        )
