from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.audio.models import Audio
from cl.citations.tasks import (
    find_citations_and_parantheticals_for_recap_documents,
)
from cl.lib.es_signal_processor import ESSignalProcessor
from cl.people_db.models import (
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    School,
)
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
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
    "reverse-delete": {
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
    "reverse-delete": {},
}

p_field_mapping = {
    "save": {
        Person: {},
    },
    "delete": {Person: {}},
    "m2m": {Person.race.through: {"person": {"races": "races"}}},
    "reverse": {
        Education: {"educations": {"all": ["school"]}},
        ABARating: {"aba_ratings": {"all": ["aba_rating"]}},
        PoliticalAffiliation: {
            "political_affiliations": {
                "all": ["political_affiliation", "political_affiliation_id"]
            }
        },
    },
    "reverse-delete": {
        Education: {"person": {"all": ["school"]}},
        ABARating: {"person": {"all": ["aba_rating"]}},
        PoliticalAffiliation: {
            "person": {
                "all": ["political_affiliation", "political_affiliation_id"]
            }
        },
    },
}

position_field_mapping = {
    "save": {
        Person: {
            "appointer__person": {
                "name_full_reverse": ["appointer"],
            },
            "predecessor": {
                "name_full_reverse": ["predecessor"],
            },
            "supervisor": {
                "name_full_reverse": ["supervisor"],
            },
            "person": {
                "name_full": ["name"],
                "religion": ["religion"],
                "gender": ["gender"],
                "dob_city": ["dob_city"],
                "dob_state": ["dob_state", "dob_state_id"],
                "fjc_id": ["fjc_id"],
                "date_dob": ["dob"],
                "date_dod": ["dod"],
            },
        },
        School: {"educations__school": {"name": ["school"]}},
        PoliticalAffiliation: {
            "political_affiliations": {
                "political_party": [
                    "political_affiliation",
                    "political_affiliation_id",
                ],
            }
        },
        ABARating: {"aba_ratings": {"rating": ["aba_rating"]}},
        Position: {},
    },
    "delete": {Position: {}},
    "m2m": {Person.race.through: {"person": {"races": "races"}}},
    "reverse": {},
    "reverse-delete": {},
}

docket_field_mapping = {
    "save": {
        Docket: {},
        Person: {
            "assigned_to": {
                "name_full": ["assignedTo"],
            },
            "referred_to": {
                "name_full": ["referredTo"],
            },
        },
    },
    "delete": {Docket: {}},
    "m2m": {},
    "reverse": {
        BankruptcyInformation: {
            "bankruptcy_information": {
                "chapter": ["chapter"],
                "trustee_str": ["trustee_str"],
            }
        },
    },
    "reverse-delete": {
        BankruptcyInformation: {"docket": {"all": ["chapter", "trustee_str"]}},
    },
}

recap_document_field_mapping = {
    "save": {
        RECAPDocument: {},
        DocketEntry: {
            "docket_entry": {
                "description": ["description"],
                "entry_number": ["entry_number"],
                "date_filed": ["entry_date_filed"],
            }
        },
        Docket: {
            "docket_entry__docket": {
                "case_name": ["caseName"],
                "case_name_full": ["case_name_full"],
                "docket_number": ["docketNumber"],
                "nature_of_suit": ["suitNature"],
                "cause": ["cause"],
                "jury_demand": ["juryDemand"],
                "jurisdiction_type": ["jurisdictionType"],
                "date_argued": ["dateArgued"],
                "date_filed": ["dateFiled"],
                "date_terminated": ["dateTerminated"],
                "assigned_to_id": ["assigned_to_id", "assignedTo"],
                "referred_to_id": ["referred_to_id", "referredTo"],
                "assigned_to_str": ["assignedTo"],
                "referred_to_str": ["referredTo"],
            }
        },
        Person: {
            "assigned_to": {
                "name_full": ["assignedTo"],
            },
            "referred_to": {
                "name_full": ["referredTo"],
            },
        },
    },
    "delete": {RECAPDocument: {}},
    "m2m": {},
    "reverse": {},
    "reverse-delete": {},
}

o_field_mapping = {
    "save": {
        Opinion: {},
    },
    "delete": {Opinion: {}},
    "m2m": {
        OpinionsCited: {
            "opinion": {
                "cites": "cites",
            },
        },
        Opinion.joined_by.through: {
            "opinion": {
                "joined_by_ids": "joined_by_ids",
            },
        },
    },
    "reverse": {},
}

o_cluster_field_mapping = {
    "save": {
        Docket: {
            "docket": {
                "court_id": ["court_exact"],
            }
        },
        Opinion: {"sub_opinions": {"cluster_id": ["sibling_ids"]}},
        OpinionCluster: {},
    },
    "delete": {OpinionCluster: {}},
    "m2m": {
        OpinionCluster.panel.through: {
            "opinioncluster": {
                "panel_ids": "panel_ids",
            },
        },
        OpinionCluster.non_participating_judges.through: {
            "opinioncluster": {
                "non_participating_judge_ids": "non_participating_judge_ids",
            },
        },
    },
    "reverse": {
        Opinion: {"sub_opinions": {"all": ["sibling_ids"]}},
        Citation: {
            "citations": {"all": ["citation", "neutralCite", "lexisCite"]}
        },
    },
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

_position_signal_processor = ESSignalProcessor(
    Position, PositionDocument, position_field_mapping
)

_docket_signal_processor = ESSignalProcessor(
    Docket, DocketDocument, docket_field_mapping
)

_recap_document_signal_processor = ESSignalProcessor(
    RECAPDocument, ESRECAPDocument, recap_document_field_mapping
)

_o_signal_processor = ESSignalProcessor(
    Opinion, OpinionDocument, o_field_mapping
)

_o_cluster_signal_processor = ESSignalProcessor(
    OpinionCluster, OpinionClusterDocument, o_cluster_field_mapping
)


@receiver(
    post_save,
    sender=RECAPDocument,
    dispatch_uid="handle_recap_doc_change_uid",
)
def handle_recap_doc_change(
    sender, instance: RECAPDocument, update_fields=None, **kwargs
):
    """
    Right now, this receiver exists to enqueue the task to parse RECAPDocuments for caselaw citations.
    More functionality can be put here later. There may be things currently in the save function
    of RECAPDocument that would be better placed here for reasons of maintainability and testability.
    """

    # Whenever pdf text is processed, it will update the plain_text field.
    # When we get updated text for a doc, we want to parse it for citations.
    if update_fields is not None and "plain_text" in update_fields:
        # Even though the task itself filters for qualifying ocr_status,
        # we don't want to clog the TQ with unncessary items.
        if instance.ocr_status in (
            RECAPDocument.OCR_COMPLETE,
            RECAPDocument.OCR_UNNECESSARY,
        ):
            find_citations_and_parantheticals_for_recap_documents.apply_async(
                args=([instance.pk],)
            )
