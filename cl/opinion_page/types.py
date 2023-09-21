from dataclasses import dataclass


@dataclass
class RECAPCitationViewData:
    depth: int
    citing_document_id: int
    cited_opinion_id: int
    cluster_slug: str
    cluster_pk: int
