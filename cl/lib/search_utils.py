import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import parse_qs, urlencode

from django.conf import settings
from django.core.cache import cache, caches
from django.http import HttpRequest, QueryDict
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from requests import Session
from scorched.response import SolrResponse

from cl.citations.match_citations import search_db_for_fullcitation
from cl.citations.utils import get_citation_depth_between_clusters
from cl.lib.bot_detector import is_bot
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.types import CleanData, SearchParam
from cl.search.constants import (
    SOLR_OPINION_HL_FIELDS,
    SOLR_ORAL_ARGUMENT_HL_FIELDS,
    SOLR_PEOPLE_HL_FIELDS,
    SOLR_RECAP_HL_FIELDS,
)
from cl.search.forms import SearchForm
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Court,
    OpinionCluster,
    RECAPDocument,
)

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
            "text": 1,
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


def get_solr_interface(
    cd: CleanData, http_connection: Session | None = None
) -> ExtraSolrInterface:
    """Get the correct solr interface for the query"""
    search_type = cd["type"]
    if search_type == SEARCH_TYPES.OPINION:
        si = ExtraSolrInterface(
            settings.SOLR_OPINION_URL,
            http_connection=http_connection,
            mode="r",
        )
    elif search_type in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        si = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=http_connection, mode="r"
        )
    elif search_type == SEARCH_TYPES.ORAL_ARGUMENT:
        si = ExtraSolrInterface(
            settings.SOLR_AUDIO_URL, http_connection=http_connection, mode="r"
        )
    elif search_type == SEARCH_TYPES.PEOPLE:
        si = ExtraSolrInterface(
            settings.SOLR_PEOPLE_URL, http_connection=http_connection, mode="r"
        )
    else:
        raise NotImplementedError(f"Unknown search type: {search_type}")

    return si


def make_get_string(
    request: HttpRequest,
    nuke_fields: Optional[List[str]] = None,
) -> str:
    """Makes a get string from the request object. If necessary, it removes
    the pagination parameters.
    """
    if nuke_fields is None:
        nuke_fields = ["page", "show_alert_modal"]
    get_dict = parse_qs(request.META["QUERY_STRING"])
    for key in nuke_fields:
        try:
            del get_dict[key]
        except KeyError:
            pass
    get_string = urlencode(get_dict, True)
    if len(get_string) > 0:
        get_string += "&"
    return get_string


def get_query_citation(cd: CleanData) -> Optional[List[FullCaseCitation]]:
    """Extract citations from the query string and return them, or return
    None
    """
    if not cd.get("q"):
        return None
    citations = get_citations(cd["q"])

    citations = [c for c in citations if isinstance(c, FullCaseCitation)]

    matches = None
    if len(citations) == 1:
        # If it's not exactly one match, user doesn't get special help.
        matches = search_db_for_fullcitation(citations[0])
        if len(matches) == 1:
            # If more than one match, don't show the tip
            return matches.result.docs[0]

    return matches


def make_stats_variable(
    search_form: SearchForm,
    paged_results: SolrResponse,
) -> List[str]:
    """Create a useful facet variable for use in a template

    This function merges the fields in the form with the facet counts from
    Solr, creating useful variables for the front end.

    We need to handle two cases:
      1. Page loads where we don't have facet values. This can happen when the
         search was invalid (bad date formatting, for example), or when the
         search itself crashed (bad Solr syntax, for example).
      2. A regular page load, where everything worked properly.

    In either case, the count value is associated with the form fields as an
    attribute named "count". If the search didn't work, the value will be None.
    If it did, the value will be an int.
    """
    facet_fields = []
    try:
        solr_facet_values = dict(
            paged_results.object_list.facet_counts.facet_fields["status_exact"]
        )
    except (AttributeError, KeyError):
        # AttributeError: Query failed.
        # KeyError: Faceting not enabled on field.
        solr_facet_values = {}

    for field in search_form:
        if not field.html_name.startswith("stat_"):
            continue

        try:
            count = solr_facet_values[field.html_name.replace("stat_", "")]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the
            # facets variable
            count = None

        field.count = count
        facet_fields.append(field)
    return facet_fields


def merge_form_with_courts(
    courts: Dict,
    search_form: SearchForm,
) -> Tuple[Dict[str, List], str, str]:
    """Merges the courts dict with the values from the search form.

    Final value is like (note that order is significant):
    courts = {
        'federal': [
            {'name': 'Eighth Circuit',
             'id': 'ca8',
             'checked': True,
             'jurisdiction': 'F',
             'has_oral_argument_scraper': True,
            },
            ...
        ],
        'district': [
            {'name': 'D. Delaware',
             'id': 'deld',
             'checked' False,
             'jurisdiction': 'FD',
             'has_oral_argument_scraper': False,
            },
            ...
        ],
        'state': [
            [{}, {}, {}][][]
        ],
        ...
    }

    State courts are a special exception. For layout purposes, they get
    bundled by supreme court and then by hand. Yes, this means new state courts
    requires manual adjustment here.
    """
    # Are any of the checkboxes checked?
    checked_statuses = [
        field.value()
        for field in search_form
        if field.html_name.startswith("court_")
    ]
    no_facets_selected = not any(checked_statuses)
    all_facets_selected = all(checked_statuses)
    court_count = str(
        len([status for status in checked_statuses if status is True])
    )
    court_count_human = court_count
    if all_facets_selected:
        court_count_human = "All"

    for field in search_form:
        if no_facets_selected:
            for court in courts:
                court.checked = True
        else:
            for court in courts:
                # We're merging two lists, so we have to do a nested loop
                # to find the right value.
                if f"court_{court.pk}" == field.html_name:
                    court.checked = field.value()
                    break

    # Build the dict with jurisdiction keys and arrange courts into tabs
    court_tabs: Dict[str, List] = {
        "federal": [],
        "district": [],
        "state": [],
        "special": [],
    }
    bap_bundle = []
    b_bundle = []
    state_bundle: List = []
    state_bundles = []
    for court in courts:
        if court.jurisdiction == Court.FEDERAL_APPELLATE:
            court_tabs["federal"].append(court)
        elif court.jurisdiction == Court.FEDERAL_DISTRICT:
            court_tabs["district"].append(court)
        elif court.jurisdiction in Court.BANKRUPTCY_JURISDICTIONS:
            # Bankruptcy gets bundled into BAPs and regular courts.
            if court.jurisdiction == Court.FEDERAL_BANKRUPTCY_PANEL:
                bap_bundle.append(court)
            else:
                b_bundle.append(court)
        elif court.jurisdiction in Court.STATE_JURISDICTIONS:
            # State courts get bundled by supreme courts
            if court.jurisdiction == Court.STATE_SUPREME:
                # Whenever we hit a state supreme court, we append the
                # previous bundle and start a new one.
                if state_bundle:
                    state_bundles.append(state_bundle)
                state_bundle = [court]
            else:
                state_bundle.append(court)
        elif court.jurisdiction in [
            Court.FEDERAL_SPECIAL,
            Court.COMMITTEE,
            Court.INTERNATIONAL,
        ]:
            court_tabs["special"].append(court)

    # append the final state bundle after the loop ends. Hack?
    state_bundles.append(state_bundle)

    # Put the bankruptcy bundles in the courts dict
    if bap_bundle:
        court_tabs["bankruptcy_panel"] = [bap_bundle]
    court_tabs["bankruptcy"] = [b_bundle]

    # Divide the state bundles into the correct partitions
    court_tabs["state"].append(state_bundles[:17])
    court_tabs["state"].append(state_bundles[17:34])
    court_tabs["state"].append(state_bundles[34:])

    return court_tabs, court_count_human, court_count


def make_fq(
    cd: CleanData,
    field: str,
    key: str,
    make_phrase: bool = False,
) -> str:
    """Does some minimal processing of the query string to get it into a
    proper field query.

    This is necessary because despite our putting AND as the default join
    method, in some cases Solr decides OR is a better approach. So, to work
    around this bug, we do some minimal query parsing ourselves:

    1. If the user provided a phrase we pass that through.

    1. Otherwise, we insert AND as a conjunction between all words.

    :param cd: The cleaned data dictionary from the form.
    :param field: The Solr field to use for the query (e.g. "caseName")
    :param key: The model form field to use for the query (e.g. "case_name")
    :param make_phrase: Whether we should wrap the query in quotes to make a
    phrase search.
    :returns A field query string like "caseName:Roe"
    """
    q = cd[key]
    q = q.replace(":", " ")

    if q.startswith('"') and q.endswith('"'):
        # User used quotes. Just pass it through.
        return f"{field}:({q})"

    if make_phrase:
        # No need to mess with conjunctions. Just wrap in quotes.
        return f'{field}:("{q}")'

    # Iterate over the query word by word. If the word is a conjunction
    # word, detect that and use the user's request. Else, make sure there's
    # an AND everywhere there should be.
    words = q.split()
    clean_q = [words[0]]
    needs_default_conjunction = True
    for word in words[1:]:
        if word.lower() in ["and", "or", "not"]:
            clean_q.append(word.upper())
            needs_default_conjunction = False
        else:
            if needs_default_conjunction:
                clean_q.append("AND")
            clean_q.append(word)
            needs_default_conjunction = True
    fq = f"{field}:({' '.join(clean_q)})"
    return fq


def make_boolean_fq(cd: CleanData, field: str, key: str) -> str:
    return f"{field}:{str(cd[key]).lower()}"


def make_fq_proximity_query(cd: CleanData, field: str, key: str) -> str:
    """Make an fq proximity query, attempting to normalize and user input.

    This neuters the citation query box, but at the same time ensures that a
    query for 22 US 44 doesn't return an item with parallel citations 22 US 88
    and 44 F.2d 92. I.e., this ensures that queries don't span citations. This
    works because internally Solr uses proximity to create multiValue fields.

    See: http://stackoverflow.com/a/33858649/64911 and
         https://github.com/freelawproject/courtlistener/issues/381
    """
    # Remove all valid Solr tokens, replacing with a space.
    q = re.sub(r'[\^\?\*:\(\)!"~\-\[\]]', " ", cd[key])

    # Remove all valid Solr words
    tokens = []
    for token in q.split():
        if token not in ["AND", "OR", "NOT", "TO"]:
            tokens.append(token)
    return f"{field}:(\"{' '.join(tokens)}\"~5)"


def make_date_query(
    query_field: str,
    before: datetime,
    after: datetime,
) -> str:
    """Given the cleaned data from a form, return a valid Solr fq string"""
    if any([before, after]):
        if hasattr(after, "strftime"):
            date_filter = f"[{after.isoformat()}T00:00:00Z TO "
        else:
            date_filter = "[* TO "
        if hasattr(before, "strftime"):
            date_filter = f"{date_filter}{before.isoformat()}T23:59:59Z]"
        else:
            date_filter = f"{date_filter}*]"
    else:
        # No date filters were requested
        return ""
    return f"{query_field}:{date_filter}"


def make_cite_count_query(cd: CleanData) -> str:
    """Given the cleaned data from a form, return a valid Solr fq string"""
    start = cd.get("cited_gt") or "*"
    end = cd.get("cited_lt") or "*"
    if start == "*" and end == "*":
        return ""
    else:
        return f"citeCount:[{start} TO {end}]"


def get_selected_field_string(cd: CleanData, prefix: str) -> str:
    """Pulls the selected checkboxes out of the form data, and puts it into
    Solr strings. Uses a prefix to know which items to pull out of the cleaned
    data. Check forms.py to see how the prefixes are set up.

    Final strings are of the form "A" OR "B" OR "C", with quotes in case there
    are spaces in the values.
    """
    selected_fields = [
        f"\"{k.replace(prefix, '')}\""
        for k, v in cd.items()
        if (k.startswith(prefix) and v is True)
    ]
    if len(selected_fields) == cd[f"_{prefix}count"]:
        # All the boxes are checked. No need for filtering.
        return ""
    else:
        selected_field_string = " OR ".join(selected_fields)
        return selected_field_string


def make_boost_string(fields: Dict[str, float]) -> str:
    qf_array = []
    for k, v in fields.items():
        qf_array.append(f"{k}^{v}")
    return " ".join(qf_array)


def add_boosts(main_params: SearchParam, cd: CleanData) -> None:
    """Add any boosts that make sense for the query."""
    if cd["type"] == SEARCH_TYPES.OPINION and main_params["sort"].startswith(
        "score"
    ):
        main_params["boost"] = "pagerank"

    # Apply standard qf parameters
    qf = BOOSTS["qf"][cd["type"]].copy()
    main_params["qf"] = make_boost_string(qf)

    if cd["type"] in [
        SEARCH_TYPES.OPINION,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.ORAL_ARGUMENT,
    ]:
        # Give a boost on the case_name field if it's obviously a case_name
        # query.
        vs_query = any(
            [
                " v " in main_params["q"],
                " v. " in main_params["q"],
                " vs. " in main_params["q"],
            ]
        )
        in_re_query = main_params["q"].lower().startswith("in re ")
        matter_of_query = main_params["q"].lower().startswith("matter of ")
        ex_parte_query = main_params["q"].lower().startswith("ex parte ")
        if any([vs_query, in_re_query, matter_of_query, ex_parte_query]):
            qf.update({"caseName": 50})
            main_params["qf"] = make_boost_string(qf)

    # Apply phrase-based boosts
    if cd["type"] in [
        SEARCH_TYPES.OPINION,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.ORAL_ARGUMENT,
    ]:
        main_params["pf"] = make_boost_string(BOOSTS["pf"][cd["type"]])
        main_params["ps"] = 5


def add_faceting(main_params: SearchParam, cd: CleanData, facet: bool) -> None:
    """Add any faceting filters to the query."""
    if not facet:
        # Faceting is off. Do nothing.
        return

    facet_params = cast(SearchParam, {})
    if cd["type"] == SEARCH_TYPES.OPINION:
        facet_params = {
            "facet": "true",
            "facet.mincount": 0,
            "facet.field": "{!ex=dt}status_exact",
        }
    main_params.update(facet_params)


def add_highlighting(
    main_params: SearchParam,
    cd: CleanData,
    highlight: Union[bool, str],
) -> None:
    """Add any parameters relating to highlighting."""

    if not highlight:
        # highlighting is off, therefore we get the default fl parameter,
        # which gives us all fields. We could set it manually, but there's
        # no need.
        return

    # Common highlighting params up here.
    main_params.update(
        {
            "hl": "true",
            "f.text.hl.snippets": "5",
            "f.text.hl.maxAlternateFieldLength": "500",
            "f.text.hl.alternateField": "text",
        }
    )

    if highlight == "text":
        main_params["hl.fl"] = "text"
        return

    assert highlight == "all", "Got unexpected highlighting value."
    # Requested fields for the main query. We only need the fields
    # here that are not requested as part of highlighting. Facet
    # params are not set here because they do not retrieve results,
    # only counts (they are set to 0 rows).
    if cd["type"] == SEARCH_TYPES.OPINION:
        fl = [
            "absolute_url",
            "citeCount",
            "court_id",
            "dateFiled",
            "download_url",
            "id",
            "cluster_id",
            "local_path",
            "sibling_ids",
            "source",
            "status",
        ]
        hlfl = SOLR_OPINION_HL_FIELDS
    elif cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        fl = [
            "absolute_url",
            "assigned_to_id",
            "attachment_number",
            "attorney",
            "court_id",
            "dateArgued",
            "dateFiled",
            "dateTerminated",
            "docket_absolute_url",
            "docket_id",
            "document_number",
            "id",
            "is_available",
            "page_count",
            "party",
            "referred_to_id",
        ]
        hlfl = SOLR_RECAP_HL_FIELDS
    elif cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        fl = [
            "id",
            "absolute_url",
            "court_id",
            "local_path",
            "source",
            "download_url",
            "docket_id",
            "dateArgued",
            "duration",
        ]
        hlfl = SOLR_ORAL_ARGUMENT_HL_FIELDS
    elif cd["type"] == SEARCH_TYPES.PEOPLE:
        fl = [
            "id",
            "absolute_url",
            "dob",
            "date_granularity_dob",
            "dod",
            "date_granularity_dod",
            "political_affiliation",
            "aba_rating",
            "school",
            "appointer",
            "supervisor",
            "predecessor",
            "selection_method",
            "court",
        ]
        hlfl = SOLR_PEOPLE_HL_FIELDS
    main_params.update({"fl": ",".join(fl), "hl.fl": ",".join(hlfl)})
    for field in hlfl:
        if field == "text":
            continue
        main_params[f"f.{field}.hl.fragListBuilder"] = "single"  # type: ignore
        main_params[f"f.{field}.hl.alternateField"] = field  # type: ignore


def add_filter_queries(main_params: SearchParam, cd) -> None:
    """Add the fq params"""
    # Changes here are usually mirrored in place_facet_queries, below.
    main_fq = []

    if cd["type"] == SEARCH_TYPES.OPINION:
        if cd["case_name"]:
            main_fq.append(make_fq(cd, "caseName", "case_name"))
        if cd["judge"]:
            main_fq.append(make_fq(cd, "judge", "judge"))
        if cd["docket_number"]:
            main_fq.append(
                make_fq(cd, "docketNumber", "docket_number", make_phrase=True)
            )
        if cd["citation"]:
            main_fq.append(make_fq_proximity_query(cd, "citation", "citation"))
        if cd["neutral_cite"]:
            main_fq.append(make_fq(cd, "neutralCite", "neutral_cite"))
        main_fq.append(
            make_date_query("dateFiled", cd["filed_before"], cd["filed_after"])
        )

        # Citation count
        cite_count_query = make_cite_count_query(cd)
        main_fq.append(cite_count_query)

    elif cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        if cd["case_name"]:
            main_fq.append(make_fq(cd, "caseName", "case_name"))
        if cd["description"]:
            main_fq.append(make_fq(cd, "description", "description"))
        if cd["docket_number"]:
            main_fq.append(
                make_fq(cd, "docketNumber", "docket_number", make_phrase=True)
            )
        if cd["nature_of_suit"]:
            main_fq.append(make_fq(cd, "suitNature", "nature_of_suit"))
        if cd["cause"]:
            main_fq.append(make_fq(cd, "cause", "cause"))
        if cd["document_number"]:
            main_fq.append(make_fq(cd, "document_number", "document_number"))
        if cd["attachment_number"]:
            main_fq.append(
                make_fq(cd, "attachment_number", "attachment_number")
            )
        if cd["assigned_to"]:
            main_fq.append(make_fq(cd, "assignedTo", "assigned_to"))
        if cd["referred_to"]:
            main_fq.append(make_fq(cd, "referredTo", "referred_to"))
        if cd["available_only"]:
            main_fq.append(
                make_boolean_fq(cd, "is_available", "available_only")
            )
        if cd["party_name"]:
            main_fq.append(make_fq(cd, "party", "party_name"))
        if cd["atty_name"]:
            main_fq.append(make_fq(cd, "attorney", "atty_name"))

        main_fq.append(
            make_date_query("dateFiled", cd["filed_before"], cd["filed_after"])
        )

    elif cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        if cd["case_name"]:
            main_fq.append(make_fq(cd, "caseName", "case_name"))
        if cd["judge"]:
            main_fq.append(make_fq(cd, "judge", "judge"))
        if cd["docket_number"]:
            main_fq.append(make_fq(cd, "docketNumber", "docket_number"))
        main_fq.append(
            make_date_query(
                "dateArgued", cd["argued_before"], cd["argued_after"]
            )
        )

    elif cd["type"] == SEARCH_TYPES.PEOPLE:
        if cd["name"]:
            main_fq.append(make_fq(cd, "name", "name"))
        if cd["dob_city"]:
            main_fq.append(make_fq(cd, "dob_city", "dob_city"))
        if cd["dob_state"]:
            main_fq.append(make_fq(cd, "dob_state_id", "dob_state"))
        if cd["school"]:
            main_fq.append(make_fq(cd, "school", "school"))
        if cd["appointer"]:
            main_fq.append(make_fq(cd, "appointer", "appointer"))
        if cd["selection_method"]:
            main_fq.append(
                make_fq(cd, "selection_method_id", "selection_method")
            )
        if cd["political_affiliation"]:
            main_fq.append(
                make_fq(
                    cd, "political_affiliation_id", "political_affiliation"
                )
            )
        main_fq.append(
            make_date_query("dob", cd["born_before"], cd["born_after"])
        )

    # Facet filters
    if cd["type"] == SEARCH_TYPES.OPINION:
        selected_stats_string = get_selected_field_string(cd, "stat_")
        if len(selected_stats_string) > 0:
            main_fq.append(
                "{!tag=dt}status_exact:(%s)" % selected_stats_string
            )

    selected_courts_string = get_selected_field_string(cd, "court_")
    if len(selected_courts_string) > 0:
        main_fq.append(f"court_exact:({selected_courts_string})")

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(main_fq) > 0:
        if "fq" in main_params:
            main_params["fq"].extend(main_fq)
        else:
            main_params["fq"] = main_fq


def map_to_docket_entry_sorting(sort_string: str) -> str:
    """Convert a RECAP sorting param to a docket entry sorting parameter."""
    if sort_string == "dateFiled asc":
        return "entry_date_filed asc"
    elif sort_string == "dateFiled desc":
        return "entry_date_filed desc"
    else:
        return sort_string


def add_grouping(main_params: SearchParam, cd: CleanData, group: bool) -> None:
    """Add any grouping parameters."""
    if cd["type"] == SEARCH_TYPES.OPINION:
        # Group clusters. Because this uses faceting, we use the collapse query
        # parser here instead of the usual result grouping. Faceting with
        # grouping has terrible performance.
        group_fq = "{!collapse field=cluster_id sort='type asc'}"
        if "fq" in main_params:
            main_params["fq"].append(group_fq)
        else:
            main_params["fq"] = [group_fq]

    elif (
        cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]
        and group is True
    ):
        docket_query = re.search(r"docket_id:\d+", cd["q"])
        if docket_query:
            group_sort = map_to_docket_entry_sorting(main_params["sort"])
        else:
            group_sort = "score desc"
        if cd["type"] == SEARCH_TYPES.RECAP:
            group_limit = 5 if not docket_query else 500
        elif cd["type"] == SEARCH_TYPES.DOCKETS:
            group_limit = 1 if not docket_query else 500
        group_params = cast(
            SearchParam,
            {
                "group": "true",
                "group.ngroups": "true",
                "group.limit": group_limit,
                "group.field": "docket_id",
                "group.sort": group_sort,
            },
        )
        main_params.update(group_params)


def regroup_snippets(results):
    """Regroup the snippets in a grouped result.

    Grouped results will have snippets for each of the group members. Some of
    the snippets will be the same because they're the same across all items in
    the group. For example, every opinion in the opinion index contains the
    name of the attorneys. So, if we have a match on the attorney name, that'll
    generate a snippet for both the lead opinion and a dissent.

    In this function, we identify these kinds of duplicates and pull them out.
    We also flatten the results so that snippets are easier to get.

    This also supports results that have been paginated and ones that have not.
    """
    if results is None:
        return

    if hasattr(results, "paginator"):
        group_field = results.object_list.group_field
    else:
        group_field = results.group_field
    if group_field is not None:
        if hasattr(results, "paginator"):
            groups = getattr(results.object_list.groups, group_field)["groups"]
        else:
            groups = results

        for group in groups:
            snippets = []
            for doc in group["doclist"]["docs"]:
                for snippet in doc["solr_highlights"]["text"]:
                    if snippet not in snippets:
                        snippets.append(snippet)
            group["snippets"] = snippets


def print_params(params: SearchParam) -> None:
    if settings.DEBUG:
        print(
            "Params sent to search are:\n%s"
            % " &\n".join(["  %s = %s" % (k, v) for k, v in params.items()])
        )
        # print results_si.execute()


def cleanup_main_query(query_string: str) -> str:
    """Enhance the query string with some simple fixes

     - Make any numerical queries into phrases (except dates)
     - Add hyphens to district docket numbers that lack them
     - Ignore tokens inside phrases
     - Handle query punctuation correctly by mostly ignoring it

    :param query_string: The query string from the form
    :return The enhanced query string
    """
    inside_a_phrase = False
    cleaned_items = []
    for item in re.split(r'([^a-zA-Z0-9_\-~":]+)', query_string):
        if not item:
            continue

        if item.startswith('"') or item.endswith('"'):
            # Start or end of a phrase; flip whether we're inside a phrase
            inside_a_phrase = not inside_a_phrase
            cleaned_items.append(item)
            continue

        if inside_a_phrase:
            # Don't do anything if we're already in a phrase query
            cleaned_items.append(item)
            continue

        not_numeric = not item[0].isdigit()
        is_date_str = re.match(
            "[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", item
        )
        if any([not_numeric, is_date_str]):
            cleaned_items.append(item)
            continue

        m = re.match(r"(\d{2})(cv|cr|mj|po)(\d{1,5})", item)
        if m:
            # It's a docket number missing hyphens, e.g. 19cv38374
            item = "-".join(m.groups())

        # Some sort of number, probably a docket number.
        # Wrap in quotes to do a phrase search
        cleaned_items.append(f'"{item}"')
    return "".join(cleaned_items)


def build_main_query(
    cd: CleanData,
    highlight: Union[bool, str] = "all",
    order_by: str = "",
    facet: bool = True,
    group: bool = True,
) -> SearchParam:
    main_params = cast(
        SearchParam,
        {
            "q": cleanup_main_query(cd["q"] or "*"),
            "sort": cd.get("order_by", order_by),
            "caller": "build_main_query",
        },
    )
    add_faceting(main_params, cd, facet)
    add_boosts(main_params, cd)
    add_highlighting(main_params, cd, highlight)
    add_filter_queries(main_params, cd)
    add_grouping(main_params, cd, group)

    print_params(main_params)
    return main_params


def build_main_query_from_query_string(
    query_string,
    updates=None,
    kwargs=None,
) -> Optional[SearchParam]:
    """Build a main query dict from a query string

    :param query_string: A GET string to build from.
    :param updates: A dict that can be added to the normal finished query
    string to override any of its defaults.
    :param kwargs: Kwargs to send to the build_main_query function
    :return: A dict that can be sent to Solr for querying
    """
    qd = QueryDict(query_string)
    search_form = SearchForm(qd)

    if not search_form.is_valid():
        return None

    cd = search_form.cleaned_data
    if kwargs is None:
        main_query = build_main_query(cd)
    else:
        main_query = build_main_query(cd, **kwargs)
    if updates is not None:
        main_query.update(updates)

    return main_query


def build_coverage_query(court: str, q: str, facet_field: str) -> SearchParam:
    """
    Create a coverage that can be used to make a facet query

    :param court: String representation of the court to filter to, e.g. 'ca1',
    defaults to 'all'.
    :param q: A query to limit the coverage query, defaults to '*'
    :param facet_field: The field to do faceting on
    :type facet_field: str
    :return: A coverage query dict
    """
    params = cast(
        SearchParam,
        {
            "facet": "true",
            "facet.range": facet_field,
            "facet.range.start": "1600-01-01T00:00:00Z",  # Assume very early date.
            "facet.range.end": "NOW/DAY",
            "facet.range.gap": "+1YEAR",
            "rows": 0,
            "q": q or "*",  # Without this, results will be omitted.
            "caller": "build_coverage_query",
        },
    )
    if court.lower() != "all":
        params["fq"] = [f"court_exact:{court}"]
    return params


def build_alert_estimation_query(cd: CleanData, day_count: int) -> SearchParam:
    """Build the parameters for estimating the frequency an alert is
    triggered.
    """
    params = cast(
        SearchParam,
        {
            "q": cleanup_main_query(cd["q"] or "*"),
            "rows": 0,
            "caller": "alert_estimator",
        },
    )
    cd["filed_after"] = date.today() - timedelta(days=day_count)
    cd["filed_before"] = None
    add_filter_queries(params, cd)

    print_params(params)
    return params


def build_court_count_query(group: bool = False) -> SearchParam:
    """Build a query that returns the count of cases for all courts

    :param group: Should the results be grouped? Note that grouped facets have
    bad performance.
    """
    params = cast(
        SearchParam,
        {
            "q": "*",
            "facet": "true",
            "facet.field": "court_exact",
            "facet.limit": -1,
            "rows": 0,
            "caller": "build_court_count_query",
        },
    )
    if group:
        params.update(
            cast(
                SearchParam,
                {
                    "group": "true",
                    "group.ngroups": "true",
                    "group.field": "docket_id",
                    "group.limit": "0",
                    "group.facet": "true",
                },
            )
        )
    return params


def add_depth_counts(
    search_data: Dict[str, Any],
    search_results: SolrResponse,
) -> Optional[OpinionCluster]:
    """If the search data contains a single "cites" term (e.g., "cites:(123)"),
    calculate and append the citation depth information between each Solr
    result and the cited OpinionCluster. We only do this for *single* "cites"
    terms to avoid the complexity of trying to render multiple depth
    relationships for all the possible result-citation combinations.

    :param search_data: The cleaned search form data
    :param search_results: Solr results from paginate_cached_solr_results()
    :return The OpinionCluster if the lookup was successful
    """
    cites_query_matches = re.findall(r"cites:\((\d+)\)", search_data["q"])
    if len(cites_query_matches) == 1:
        try:
            cited_cluster = OpinionCluster.objects.get(
                sub_opinions__pk=cites_query_matches[0]
            )
        except OpinionCluster.DoesNotExist:
            return None
        else:
            for result in search_results.object_list:
                result["citation_depth"] = get_citation_depth_between_clusters(
                    citing_cluster_pk=result["cluster_id"],
                    cited_cluster_pk=cited_cluster.pk,
                )
            return cited_cluster
    else:
        return None


def get_citing_clusters_with_cache(
    cluster: OpinionCluster,
) -> Tuple[list, int]:
    """Use Solr to get clusters citing the one we're looking at

    :param cluster: The cluster we're targeting
    :type cluster: OpinionCluster
    :return: A tuple of the list of solr results and the number of results
    """
    cache_key = f"citing:{cluster.pk}"
    cache = caches["db_cache"]
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return cached_results

    # Cache miss. Get the citing results from Solr
    sub_opinion_pks = cluster.sub_opinions.values_list("pk", flat=True)
    ids_str = " OR ".join([str(pk) for pk in sub_opinion_pks])
    q = {
        "q": f"cites:({ids_str})",
        "rows": 5,
        "start": 0,
        "sort": "citeCount desc",
        "caller": "view_opinion",
        "fl": "absolute_url,caseName,dateFiled",
    }
    conn = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")
    results = conn.query().add_extra(**q).execute()
    conn.conn.http_connection.close()
    citing_clusters = list(results)
    citing_cluster_count = results.result.numFound
    a_week = 60 * 60 * 24 * 7
    cache.set(cache_key, (citing_clusters, citing_cluster_count), a_week)

    return citing_clusters, citing_cluster_count


def get_related_clusters_with_cache(
    cluster: OpinionCluster,
    request: HttpRequest,
) -> Tuple[List[OpinionCluster], List[int], Dict[str, str]]:
    """Use Solr to get related opinions with Solr-MoreLikeThis query

    :param cluster: The cluster we're targeting
    :param request: Request object for checking if user is permitted
    :return: A list of related clusters, a list of sub-opinion IDs, and a dict
    of URL parameters
    """

    # By default all statuses are included
    available_statuses = dict(PRECEDENTIAL_STATUS.NAMES).values()
    url_search_params = {f"stat_{v}": "on" for v in available_statuses}

    # Opinions that belong to the targeted cluster
    sub_opinion_ids = cluster.sub_opinions.values_list("pk", flat=True)

    if is_bot(request) or not sub_opinion_ids:
        # If it is a bot or lacks sub-opinion IDs, return empty results
        return [], [], url_search_params

    si = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")

    # Use cache if enabled
    mlt_cache_key = f"mlt-cluster:{cluster.pk}"
    related_clusters = (
        caches["db_cache"].get(mlt_cache_key)
        if settings.RELATED_USE_CACHE
        else None
    )

    if related_clusters is None:
        # Cache is empty

        # Turn list of opinion IDs into list of Q objects
        sub_opinion_queries = [si.Q(id=sub_id) for sub_id in sub_opinion_ids]

        # Take one Q object from the list
        sub_opinion_query = sub_opinion_queries.pop()

        # OR the Q object with the ones remaining in the list
        for item in sub_opinion_queries:
            sub_opinion_query |= item

        # Set MoreLikeThis parameters
        # (see https://lucene.apache.org/solr/guide/6_6/other-parsers.html#OtherParsers-MoreLikeThisQueryParser)
        mlt_params = {
            "fields": "text",
            "count": settings.RELATED_COUNT,
            "maxqt": settings.RELATED_MLT_MAXQT,
            "mintf": settings.RELATED_MLT_MINTF,
            "minwl": settings.RELATED_MLT_MINWL,
            "maxwl": settings.RELATED_MLT_MAXWL,
            "maxdf": settings.RELATED_MLT_MAXDF,
        }

        mlt_query = (
            si.query(sub_opinion_query)
            .mlt(**mlt_params)
            .field_limit(fields=["id", "caseName", "absolute_url"])
        )

        if settings.RELATED_FILTER_BY_STATUS:
            # Filter results by status (e.g., Precedential)
            mlt_query = mlt_query.filter(
                status_exact=settings.RELATED_FILTER_BY_STATUS
            )

            # Update URL parameters accordingly
            url_search_params = {
                f"stat_{settings.RELATED_FILTER_BY_STATUS}": "on"
            }

        mlt_res = mlt_query.execute()

        if hasattr(mlt_res, "more_like_this"):
            # Only a single sub opinion
            related_clusters = mlt_res.more_like_this.docs
        elif hasattr(mlt_res, "more_like_these"):
            # Multiple sub opinions

            # Get result list for each sub opinion
            sub_docs = [
                sub_res.docs
                for sub_id, sub_res in mlt_res.more_like_these.items()
            ]

            # Merge sub results by interleaving
            # - exclude items that are sub opinions
            related_clusters = [
                item
                for pair in zip(*sub_docs)
                for item in pair
                if item["id"] not in sub_opinion_ids
            ]

            # Limit number of results
            related_clusters = related_clusters[: settings.RELATED_COUNT]
        else:
            # No MLT results are available (this should not happen)
            related_clusters = []

        cache.set(
            mlt_cache_key, related_clusters, settings.RELATED_CACHE_TIMEOUT
        )
    si.conn.http_connection.close()
    return related_clusters, sub_opinion_ids, url_search_params


def get_mlt_query(
    si: ExtraSolrInterface,
    cd: CleanData,
    facet: bool,
    seed_pks: List[str],
    filter_query: str,
) -> SolrResponse:
    """
    By default Solr MoreLikeThis queries do not support highlighting. Thus, we
    use a special search interface and build the Solr query manually.

    :param si: SolrInterface
    :param cd: Cleaned search form data
    :param facet: Set to True to enable facets
    :param seed_pks: List of IDs of the documents for that related documents
    should be returned
    :param filter_query:
    :return: Executed SolrSearch
    """
    hl_fields = list(SOLR_OPINION_HL_FIELDS)

    # Exclude citations from MLT highlighting
    hl_fields.remove("citation")

    # Reset query for query builder
    cd["q"] = ""

    # Build main query as always
    q = build_main_query(cd, facet=facet)
    cleaned_fq = filter_query.strip()

    q.update(
        {
            "caller": "mlt_query",
            "q": f"id:({' OR '.join(seed_pks)})",
            "mlt": "true",  # Python boolean does not work here
            "mlt.fl": "text",
            "mlt.maxqt": settings.RELATED_MLT_MAXQT,
            "mlt.mintf": settings.RELATED_MLT_MINTF,
            "mlt.minwl": settings.RELATED_MLT_MINWL,
            "mlt.maxwl": settings.RELATED_MLT_MAXWL,
            "mlt.maxdf": settings.RELATED_MLT_MAXDF,
            # Retrieve fields as highlight replacement
            "fl": f"{q['fl']},{','.join(hl_fields)}",
            # Original query as filter query
            "fq": q["fq"] + [cleaned_fq],
            # unset fields not used for MLT
            "boost": "",
            "pf": "",
            "ps": "",
            "qf": "",
        }
    )

    return si.mlt_query(hl_fields).add_extra(**q)


def clean_up_recap_document_file(item: RECAPDocument) -> None:
    """Clean up the RecapDocument file-related fields after detecting the file
    doesn't exist in the storage.

    :param item: The RECAPDocument to work on.
    :return: None
    """

    if type(item) == RECAPDocument:
        item.filepath_local.delete()
        item.sha1 = ""
        item.date_upload = None
        item.file_size = None
        item.page_count = None
        item.is_available = False
        item.save()
