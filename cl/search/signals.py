from cl.lib.custom_es_signal_processor import CustomSignalProcessor
from cl.search.models import (
    Docket,
    Opinion,
    OpinionCluster,
    Parenthetical,
    ParentheticalGroup,
)

signal_processor = CustomSignalProcessor

models_save = {
    Docket: {
        "opinion__cluster__docket": {
            "docket_number": ("docketNumber", "raw"),
            "court_id": ("court_id", "raw"),
        }
    },
    Opinion: {
        "opinion": {
            "author_id": ("author_id", "raw"),
            "cluster_id": ("cluster_id", "raw"),
            "extracted_by_ocr": ("opinion_extracted_by_ocr", "raw"),
        },
    },
    OpinionCluster: {
        "representative__describing_opinion__cluster": {
            "slug": ("describing_opinion_cluster_slug", "raw")
        },
        "opinion__cluster": {
            "case_name": ("caseName", "raw"),
            "citation_count": ("citeCount", "raw"),
            "date_filed": ("dateFiled", "raw"),
            "slug": ("opinion_cluster_slug", "raw"),
            "docket_id": ("docket_id", "raw"),
            "judges": ("judge", "raw"),
            "nature_of_suit": ("suitNature", "raw"),
            "precedential_status": (
                "status",
                "display",
            ),  # This should be returned as display()
        },
    },
    Parenthetical: {
        "representative": {
            "score": ("representative_score", "raw"),
            "text": ("representative_text", "raw"),
        },
    },
    ParentheticalGroup: {},
}


signal_processor((ParentheticalGroup, [models_save]))
