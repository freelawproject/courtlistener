from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from elasticsearch_dsl import Document

from cl.alerts.send_alerts import send_or_schedule_alerts
from cl.audio.models import Audio
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import es_index_exists
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
    ParentheticalGroupDocument,
    PersonDocument,
    PositionDocument,
)
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

oa_field_mapping = {
    "save": {
        Docket: {
            "docket": {
                "date_argued": "dateArgued",
                "date_reargued": "dateReargued",
                "date_reargument_denied": "dateReargumentDenied",
                "docket_number": "docketNumber",
                "slug": "docket_slug",
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
    },
}


position_field_mapping = {
    "save": {
        Position: {},
    },
    "delete": {Position: {}},
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


@receiver(
    post_save,
    sender=PoliticalAffiliation,
    dispatch_uid="create_or_update_political_affiliation_in_es_index",
)
def create_or_update_affiliation_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Education instance is saved.
    This method creates or updates an Education object in the EducationDocument
    index.
    """

    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists(PersonDocument._index._name)
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        doc = PersonDocument.get(id=instance.person.pk)
        political_affiliation = getattr(doc, "prepare_political_affiliation")(
            instance.person
        )
        political_affiliation_id = getattr(
            doc, "prepare_political_affiliation_id"
        )(instance.person)

        Document.update(
            doc,
            **{
                "political_affiliation": political_affiliation,
                "political_affiliation_id": political_affiliation_id,
            },
        )
