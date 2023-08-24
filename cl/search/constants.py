# Solr fields that are used for highlighting or other output in the search results
import re

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
    "transcript",
    "transcript.exact",
]
SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS = [
    "text",
    "text.exact",
]
SOLR_PEOPLE_HL_FIELDS = ["name", "dob_city", "dob_state", "name_reverse"]
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
