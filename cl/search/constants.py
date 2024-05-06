# Solr fields that are used for highlighting or other output in the search results
import re
from typing import Dict

from cl.search.models import SEARCH_TYPES, Opinion

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
SOLR_PEOPLE_HL_FIELDS = ["name", "dob_city", "dob_state", "name_reverse"]
PEOPLE_ES_HL_FIELDS = [
    "name",
    "dob_city",
    "political_affiliation",
    "school",
]
PEOPLE_ES_HL_KEYWORD_FIELDS = [
    "dob_state_id",
]

# ES fields that are used in the search queries
SEARCH_ORAL_ARGUMENT_QUERY_FIELDS = [
    "court",
    "court_citation_string",
    "judge",
    "dateArgued_text",
    "dateReargued_text",
    "dateReargumentDenied_text",
    "court_id_text",
    "sha1",
]
SEARCH_PEOPLE_CHILD_QUERY_FIELDS = [
    "position_type",
    "nomination_process",
    "judicial_committee_action",
    "selection_method",
    "termination_reason",
    "court_full_name",
    "court_citation_string",
    "court_exact",
    "organization_name",
    "job_title",
]
SEARCH_PEOPLE_PARENT_QUERY_FIELDS = [
    "gender",
    "alias",
    "dob_city",
    "political_affiliation",
    "religion",
    "fjc_id",
    "aba_rating",
    "school",
]
SEARCH_RECAP_CHILD_QUERY_FIELDS = [
    "case_name_full",
    "suitNature",
    "juryDemand",
    "cause",
    "assignedTo",
    "referredTo",
    "court",
    "court_id",
    "court_citation_string",
    "chapter",
    "trustee_str",
    "short_description",
    "plain_text",
    "document_type",
]
SEARCH_RECAP_PARENT_QUERY_FIELDS = [
    "case_name_full",
    "suitNature",
    "cause",
    "juryDemand",
    "assignedTo",
    "referredTo",
    "court",
    "court_id",
    "court_citation_string",
    "chapter",
    "trustee_str",
]
SEARCH_OPINION_QUERY_FIELDS = [
    "court",
    "court_id",
    "citation",
    "judge",
    "caseNameFull",
    "caseName",
    "status",
    "suitNature",
    "attorney",
    "procedural_history",
    "posture",
    "syllabus",
]

# ES fields that are used for highlighting
SEARCH_HL_TAG = "mark"
ALERTS_HL_TAG = "strong"
SEARCH_ORAL_ARGUMENT_HL_FIELDS = [
    "text",
    "caseName",
    "judge",
    "docketNumber",
    "court_citation_string",
]
SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS = [
    "caseName",
    "judge",
    "docketNumber",
    "court_citation_string",
    "text",
]
SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS = [
    "text",
    "docketNumber",
    "judge",
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
SEARCH_RECAP_HL_FIELDS = [
    "assignedTo",
    "caseName",
    "cause",
    "court_citation_string",
    "docketNumber",
    "juryDemand",
    "referredTo",
    "suitNature",
]

SEARCH_OPINION_HL_FIELDS = [
    "caseName",
    "citation",
    "court_citation_string",
    "docketNumber",
    "suitNature",
]

SEARCH_ALERTS_OPINION_HL_FIELDS = {
    "caseName": 0,
    "docketNumber": 0,
    "text": 500,
}


# In RECAP Search, it is necessary to display 'plain_text' as a truncated snippet,
# where the snippet length is determined by 'fragment_size'.
# For all other fields, the complete content should be returned.
# To specify the 'fragment_size', set its value to 0 for no truncation,
# or provide a different integer to limit the snippet length.
SEARCH_RECAP_CHILD_HL_FIELDS = {
    "short_description": 0,
    "description": 0,
    "plain_text": 100,
}
SEARCH_OPINION_CHILD_HL_FIELDS = {
    "text": 100,
}
SEARCH_RECAP_CHILD_EXCLUDE_FIELDS = {
    "plain_text": 100,
}


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
recap_boosts_es = {
    # Docket fields
    "caseName": 4.0,
    "docketNumber": 3.0,
    # RECAPDocument fields:
    "description": 2.0,
}
recap_boosts_pf = {"text": 3.0, "caseName": 3.0, "description": 3.0}
BOOSTS: Dict[str, Dict[str, Dict[str, float]]] = {
    "qf": {
        SEARCH_TYPES.OPINION: {
            "text": 1.0,
            "type": 1.0,
            # Cluster fields
            "caseName": 4.0,
            "docketNumber": 2.0,
        },
        SEARCH_TYPES.RECAP: recap_boosts_qf,
        SEARCH_TYPES.DOCKETS: recap_boosts_qf,
        SEARCH_TYPES.RECAP_DOCUMENT: recap_boosts_qf,
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
    "es": {
        SEARCH_TYPES.RECAP: recap_boosts_es,
        SEARCH_TYPES.DOCKETS: recap_boosts_es,
        SEARCH_TYPES.RECAP_DOCUMENT: recap_boosts_es,
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


o_type_index_map = {
    Opinion.COMBINED: "combined-opinion",
    Opinion.UNANIMOUS: "unanimous-opinion",
    Opinion.LEAD: "lead-opinion",
    Opinion.PLURALITY: "plurality-opinion",
    Opinion.CONCURRENCE: "concurrence-opinion",
    Opinion.CONCUR_IN_PART: "in-part-opinion",
    Opinion.DISSENT: "dissent",
    Opinion.ADDENDUM: "addendum",
    Opinion.REMITTUR: "remittitur",
    Opinion.REHEARING: "rehearing",
    Opinion.ON_THE_MERITS: "on-the-merits",
    Opinion.ON_MOTION_TO_STRIKE: "on-motion-to-strike",
}
