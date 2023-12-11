from dataclasses import InitVar, dataclass, field
from typing import Literal

from cl.search.models import (
    OpinionCluster,
    OpinionsCitedByRECAPDocument,
    RECAPDocument,
)


@dataclass
class ViewAuthority:
    caption: str
    count: int
    url: str


@dataclass
class AuthoritiesContext:
    citation_record: InitVar[OpinionCluster | RECAPDocument]
    query_string: InitVar[str]
    full_list_authorities: list[
        OpinionCluster | OpinionsCitedByRECAPDocument
    ] = field(init=False)
    total_authorities_count: int
    top_authorities: list[ViewAuthority] = field(init=False)
    view_all_url: str
    doc_type: Literal["opinion", "document"]
    query_all_authorities: bool = False

    def __post_init__(self, citation_record, query_string):
        if isinstance(citation_record, RECAPDocument):
            self.full_list_authorities = citation_record.authorities_with_data

            if self.query_all_authorities:
                # Evaluate and cache the queryset to reused the data for subsequent
                # calculations and minimizes the number of database queries required
                # to compute the values of "top_authorities" and the full list of
                # authorities in Django templates.
                list(self.full_list_authorities)

            self.top_authorities = [
                ViewAuthority(
                    caption=record.cited_opinion.cluster.caption,
                    count=record.depth,
                    url=f"{record.cited_opinion.cluster.get_absolute_url()}?{query_string}",
                )
                for record in self.full_list_authorities[:5]
            ]
        else:
            self.top_authorities = [
                ViewAuthority(
                    caption=record.caption,
                    count=record.citation_depth,
                    url=f"{record.get_absolute_url()}?{query_string}",
                )
                for record in citation_record.authorities_with_data[:5]
            ]
