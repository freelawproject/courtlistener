from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.audio.models import Audio
from cl.citations.tasks import (
    find_citations_and_parantheticals_for_recap_documents,
)
from cl.lib.es_signal_processor import ESSignalProcessor
from cl.search.documents import AudioDocument, ParentheticalGroupDocument
from cl.search.models import (
    Citation,
    Docket,
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
    update_fields = kwargs.get("update_fields", [])

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
                args=([instance.pk])
            )
