from dataclasses import dataclass
from typing import List, Literal

from django.urls import reverse

from cl.search.models import OpinionCluster, OpinionsCitedByRECAPDocument


@dataclass
class RECAPDocCitationRecord:
    total_citation_count: int
    cit_records: List[OpinionsCitedByRECAPDocument]


@dataclass
class ViewAuthority:
    caption: str
    count: int
    url: str

    @classmethod
    def from_cluster_authority(cls, auth: OpinionCluster, query_string: str):
        opinion_url = f"{auth.get_absolute_url()}?{query_string}"
        citation_count = auth.citation_depth
        opinion_caption = auth.caption
        return cls(
            caption=opinion_caption, count=citation_count, url=opinion_url
        )

    @classmethod
    def from_recap_cit_record(
        cls, record: OpinionsCitedByRECAPDocument, query_string: str
    ):
        opinion_caption = record.cited_opinion.cluster.caption
        citation_count = record.depth
        opinion_url = (
            f"{record.cited_opinion.cluster.get_absolute_url()}?{query_string}"
        )
        return cls(
            caption=opinion_caption, count=citation_count, url=opinion_url
        )


@dataclass
class AuthoritiesContext:
    total_authorities_count: int
    top_authorities: List[ViewAuthority]
    view_all_url: str
    doc_type: Literal["opinion", "document"]

    @classmethod
    def construct(
        cls,
        citation_record: OpinionCluster | RECAPDocCitationRecord,
        request_query_string: str,
    ):
        if isinstance(citation_record, OpinionCluster):
            top_authorities = [
                ViewAuthority.from_cluster_authority(ca, request_query_string)
                for ca in citation_record.authorities_with_data[:5]
            ]
            view_all_url_base = reverse(
                "view_authorities",
                args=[citation_record.pk, citation_record.slug],
            )
            total_authorities_count = len(
                citation_record.authorities_with_data
            )
            doc_type = "opinion"

        elif isinstance(citation_record, RECAPDocCitationRecord):
            top_authorities = [
                ViewAuthority.from_recap_cit_record(
                    cit_record, request_query_string
                )
                for cit_record in citation_record.cit_records
            ]
            view_all_url_base = ""  # TODO
            total_authorities_count = citation_record.total_citation_count
            doc_type = "document"

        return cls(
            top_authorities=top_authorities,
            total_authorities_count=total_authorities_count,
            view_all_url=view_all_url_base,
            doc_type=doc_type,
        )

    # @classmethod
    # def from_opinion_cluster(
    #     cls, cluster: OpinionCluster, request_query_string: str
    # ):
    #     top_authorities = [
    #         ViewAuthority.from_cluster_authority(ca, request_query_string)
    #         for ca in cluster.authorities_with_data[:5]
    #     ]
    #     view_all_url_base = reverse(
    #         "view_authorities", args=[cluster.pk, cluster.slug]
    #     )
    #     return cls(
    #         top_authorities=top_authorities,
    #         view_all_url=f"{view_all_url_base}?{request_query_string}",
    #         total_authorities_count=len(cluster.authorities_with_data),
    #     )

    # @classmethod
    # def from_recap_document_cits(
    #     cls,
    #     total_cit_count: int,
    #     cit_records: List[OpinionsCitedByRECAPDocument],
    #     request_query_string: str,
    # ):
    #     top_authorities = [
    #         ViewAuthority.from_recap_cit_record(
    #             r, query_string=request_query_string
    #         )
    #         for r in cit_records
    #     ]
    #     # TODO
    #     view_all_url_base = ""
    #     return cls(
    #         top_authorities=top_authorities,
    #         total_authorities_count=total_cit_count,
    #         view_all_url=view_all_url_base,
    #     )
