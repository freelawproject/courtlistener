from cl.lib.custom_es_signal_processor import ESSignalProcessor
from cl.search.documents import ParentheticalGroupDocument
from cl.search.models import (
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    ParentheticalGroup,
)

pa_fields_mapping = {
    "save": {
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
    },
    "delete": {ParentheticalGroup: {}},
    "m2m": {
        OpinionCluster.panel.through: {
            "opinion__cluster": {
                "panel_ids": ("panel_ids", "raw"),
            },
        },
        OpinionsCited: {
            "opinion": {
                "cites": ("cites", "raw"),
            },
        },
    },
    "reverse": {
        Citation: {
            "opinion__cluster": {
                "all": ["citation"],
                Citation.NEUTRAL: ["citation", "neutralCite"],
                Citation.LEXIS: ["citation", "lexisCite"],
            },
        }
    },
}

pa_signal_processor = ESSignalProcessor
pa_signal_processor(
    (ParentheticalGroup, ParentheticalGroupDocument, pa_fields_mapping)
)
