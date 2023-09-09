from cl.audio.models import Audio
from cl.lib.es_signal_processor import ESSignalProcessor
from cl.people_db.models import (
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    Position,
)
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    ParentheticalGroupDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
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
                "docket_number": ["docketNumber"],
                "court_id": ["court_id"],
            }
        },
        Opinion: {
            "opinion": {
                "author_id": ["author_id"],
                "cluster_id": ["cluster_id"],
                "extracted_by_ocr": ["opinion_extracted_by_ocr"],
            },
        },
        OpinionCluster: {
            "representative__describing_opinion__cluster": {
                "slug": ["describing_opinion_cluster_slug"],
            },
            "opinion__cluster": {
                "case_name": ["caseName"],
                "citation_count": ["citeCount"],
                "date_filed": ["dateFiled"],
                "slug": ["opinion_cluster_slug"],
                "docket_id": ["docket_id"],
                "judges": ["judge"],
                "nature_of_suit": ["suitNature"],
                "get_precedential_status_display": [
                    "status"
                ],  # On fields where
                # indexed values needs to be the display() value, use get_{field_name}_display as key.
            },
        },
        Parenthetical: {
            "representative": {
                "score": ["representative_score"],
                "text": ["representative_text"],
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

oa_field_mapping = {
    "save": {
        Docket: {
            "docket": {
                "date_argued": ["dateArgued", "dateArgued_text"],
                "date_reargued": ["dateReargued", "dateReargued_text"],
                "date_reargument_denied": [
                    "dateReargumentDenied",
                    "dateReargumentDenied_text",
                ],
                "docket_number": ["docketNumber"],
                "slug": ["docket_slug"],
            }
        },
        Audio: {},
    },
    "delete": {Audio: {}},
    "m2m": {Audio.panel.through: {"audio": {"panel_ids": "panel_ids"}}},
    "reverse": {},
}

p_field_mapping = {
    "save": {
        Person: {},
    },
    "delete": {Person: {}},
    "m2m": {},
    "reverse": {
        Education: {"educations": {"all": ["school"]}},
        ABARating: {"aba_ratings": {"all": ["aba_rating"]}},
        PoliticalAffiliation: {
            "political_affiliations": {
                "all": ["political_affiliation", "political_affiliation_id"]
            }
        },
    },
}


position_field_mapping = {
    "save": {
        Person: {"appointer__person": {"name_full_reverse": "appointer"}},
        Position: {},
    },
    "delete": {Position: {}},
    "m2m": {},
    "reverse": {},
}

docket_field_mapping = {
    "save": {
        Docket: {},
    },
    "delete": {Docket: {}},
    "m2m": {},
    "reverse": {
        BankruptcyInformation: {
            "bankruptcy_information": {"all": ["chapter", "trustee_str"]}
        },
    },
}

recap_document_field_mapping = {
    "save": {
        RECAPDocument: {},
        DocketEntry: {
            "docket_entry": {
                "description": ["description"],
                "entry_number": ["entry_number"],
                "date_filed": ["entry_date_filed", "entry_date_filed_text"],
            }
        },
    },
    "delete": {RECAPDocument: {}},
    "m2m": {},
    "reverse": {},
}


# Instantiate a new ESSignalProcessor() for each Model/Document that needs to
# be tracked. The arguments are: main model, ES document mapping, and field mapping dict.
_pa_signal_processor = ESSignalProcessor(
    ParentheticalGroup,
    ParentheticalGroupDocument,
    pa_field_mapping,
)

_oa_signal_processor = ESSignalProcessor(
    Audio,
    AudioDocument,
    oa_field_mapping,
)

_p_signal_processor = ESSignalProcessor(
    Person, PersonDocument, p_field_mapping
)

_position_signañ_processor = ESSignalProcessor(
    Position, PositionDocument, position_field_mapping
)

_docket_signal_processor = ESSignalProcessor(
    Docket, DocketDocument, docket_field_mapping
)

_recap_document_signal_processor = ESSignalProcessor(
    RECAPDocument, ESRECAPDocument, recap_document_field_mapping
)
