# Solr fields that are used for highlighting or other output in the search results
import re
from typing import Dict

from cl.search.models import SEARCH_TYPES

SOLR_OPINION_HL_FIELDS = [
    "caseName",
    "citation",
    "court_citation_string",
    "docketNumber",
    "judge",
    "lexisCite",
    "neutralCite",
    "suitNature",
    "text",
]
SOLR_RECAP_HL_FIELDS = [
    "assignedTo",
    "caseName",
    "cause",
    "court_citation_string",
    "docketNumber",
    "juryDemand",
    "referredTo",
    "short_description",
    "suitNature",
    "text",
]
SEARCH_ORAL_ARGUMENT_HL_FIELDS = [
    "text",
    "caseName",
    "judge",
    "docketNumber",
    "court_citation_string",
]
SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS = [
    "caseName",
    "caseName.exact",
    "judge",
    "judge.exact",
    "docketNumber",
    "docketNumber.exact",
    "court_citation_string",
    "text",
    "text.exact",
]
SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS = [
    "text",
    "text.exact",
    "docketNumber",
    "docketNumber.exact",
    "judge",
    "judge.exact",
]
SOLR_PEOPLE_HL_FIELDS = ["name", "dob_city", "dob_state", "name_reverse"]
SOLR_PEOPLE_ES_HL_FIELDS = [
    "name",
    "name.exact",
    "dob_city",
    "dob_state_id",
    "text",
    "text.exact",
]
SEARCH_HL_TAG = "mark"
ALERTS_HL_TAG = "strong"


# Search query for related items
RELATED_PATTERN = re.compile(
    r"""
    (^|\s)                      # beginning of string or whitespace
    (?P<pfx>related:            # "related:" query prefix
        (?P<pks>(               # find related items for these IDs
            ([0-9]+)(,[0-9]+)*  # one or more integers (comma separated)
            )
        )
    )
    ($|\s)                      # end of string or whitespace
    """,
    re.VERBOSE,
)

# Search Boosts
recap_boosts_qf = {
    "text": 1.0,
    "caseName": 4.0,
    "docketNumber": 3.0,
    "description": 2.0,
}
recap_boosts_pf = {"text": 3.0, "caseName": 3.0, "description": 3.0}
BOOSTS: Dict[str, Dict[str, Dict[str, float]]] = {
    "qf": {
        SEARCH_TYPES.OPINION: {
            "text": 1.0,
            "caseName": 4.0,
            "docketNumber": 2.0,
        },
        SEARCH_TYPES.RECAP: recap_boosts_qf,
        SEARCH_TYPES.DOCKETS: recap_boosts_qf,
        SEARCH_TYPES.ORAL_ARGUMENT: {
            "text": 1.0,
            "caseName": 4.0,
            "docketNumber": 2.0,
        },
        SEARCH_TYPES.PEOPLE: {
            # Was previously 4, but that had bad results for the name "William"
            # due to Williams and Mary College.
            "name": 8,
            # Suppress these fields b/c a match on them returns the wrong
            # person.
            "appointer": 0.3,
            "supervisor": 0.3,
            "predecessor": 0.3,
        },
    },
    # Phrase-based boosts.
    "pf": {
        SEARCH_TYPES.OPINION: {"text": 3.0, "caseName": 3.0},
        SEARCH_TYPES.RECAP: recap_boosts_pf,
        SEARCH_TYPES.DOCKETS: recap_boosts_pf,
        SEARCH_TYPES.ORAL_ARGUMENT: {"caseName": 3.0},
        SEARCH_TYPES.PEOPLE: {
            # None here. Phrases don't make much sense for people.
        },
    },
}
