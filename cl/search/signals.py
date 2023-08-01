from cl.lib.es_signal_processor import ESSignalProcessor
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

# This field mapping is used to define which fields should be updated in the
# Elasticsearch index document when they change in the DB. The outer keys
# represent the actions that will trigger signals:
# save: On model save
# delete: On model delete
# m2m: On many-to-many field changes
# reverse: On ForeignKey reverse relation changes
# For every action key, a dict for each Model that needs to be tracked should
# be added, where the key for these child dicts is the Model.
# In each Model dict, another dict should be added for every query relation
# (relative to the main model) that needs to be tracked. The key for these
# dicts is the query path relative to the main model:
# e.g: opinion__cluster__docket relative to ParentheticalGroup.
# Within each of these dicts, an additional dict containing tracked fields
# should be added. Keys should be the field name on the Model and values
# should be the field name in the ES document.

pa_field_mapping = {
    "save": {
        Docket: {
            "opinion__cluster__docket": {
                "docket_number": "docketNumber",
                "court_id": "court_id",
            }
        },
        Opinion: {
            "opinion": {
                "author_id": "author_id",
                "cluster_id": "cluster_id",
                "extracted_by_ocr": "opinion_extracted_by_ocr",
            },
        },
        OpinionCluster: {
            "representative__describing_opinion__cluster": {
                "slug": "describing_opinion_cluster_slug",
            },
            "opinion__cluster": {
                "case_name": "caseName",
                "citation_count": "citeCount",
                "date_filed": "dateFiled",
                "slug": "opinion_cluster_slug",
                "docket_id": "docket_id",
                "judges": "judge",
                "nature_of_suit": "suitNature",
                "get_precedential_status_display": "status",  # On fields where
                # indexed values needs to be the display() value, use get_{field_name}_display as key.
            },
        },
        Parenthetical: {
            "representative": {
                "score": "representative_score",
                "text": "representative_text",
            },
        },
        ParentheticalGroup: {},  # For the main model, a field mapping is not
        # required, since all its fields will be indexed/updated.
    },
    "delete": {ParentheticalGroup: {}},  # Delete action, this only applies to
    # the main model, no field mapping is required.
    "m2m": {
        OpinionCluster.panel.through: {
            "opinion__cluster": {
                "panel_ids": "panel_ids",
            },
        },
        OpinionsCited: {
            "opinion": {
                "cites": "cites",
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

# Instantiate a new ESSignalProcessor() for each Model/Document that needs to
# be tracked. The arguments are: main model, ES document mapping, and field mapping dict.
_pa_signal_processor = ESSignalProcessor(
    ParentheticalGroup,
    ParentheticalGroupDocument,
    pa_field_mapping,
)
