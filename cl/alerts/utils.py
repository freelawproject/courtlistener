import copy
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict
from elasticsearch_dsl import MultiSearch, Q, Search
from elasticsearch_dsl.query import Query
from elasticsearch_dsl.response import Hit, Response
from redis import Redis

from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    Alert,
    DocketAlert,
    ScheduledAlertHit,
)
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import (
    add_es_highlighting,
    add_fields_boosting,
    build_fulltext_query,
    build_has_child_filters,
    build_highlights_dict,
    build_join_es_filters,
    merge_highlights_into_result,
)
from cl.lib.types import CleanData
from cl.search.constants import (
    ALERTS_HL_TAG,
    SEARCH_RECAP_CHILD_HL_FIELDS,
    SEARCH_RECAP_CHILD_QUERY_FIELDS,
    SEARCH_RECAP_HL_FIELDS,
    docket_document_filters,
    recap_document_filters,
)
from cl.search.documents import (
    AudioDocument,
    AudioPercolator,
    DocketDocument,
    DocketDocumentPercolator,
    ESRECAPDocumentPlain,
    RECAPDocumentPercolator,
    RECAPPercolator,
)
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.types import ESDictDocument


@dataclass
class DocketAlertReportObject:
    da_alert: DocketAlert
    docket: Docket


class OldAlertReport:
    def __init__(self):
        self.old_alerts = []
        self.very_old_alerts = []
        self.disabled_alerts = []

    @property
    def old_dockets(self):
        return [obj.docket for obj in self.old_alerts]

    @property
    def very_old_dockets(self):
        return [obj.docket for obj in self.very_old_alerts]

    @property
    def disabled_dockets(self):
        return [obj.docket for obj in self.disabled_alerts]

    def total_count(self):
        return (
            len(self.old_alerts)
            + len(self.very_old_alerts)
            + len(self.disabled_alerts)
        )


class InvalidDateError(Exception):
    pass


def create_percolator_search_query(
    index_name: str, final_query: Query, search_after: int | None = None
):
    """Create an Elasticsearch search query with pagination.

    :param index_name: The name of the Elasticsearch index to search.
    :param final_query: Elasticsearch DSL Query object.
    :param search_after: An optional parameter for search_after pagination.
    :return: An Elasticsearch search object with the specified query and pagination settings.
    """

    s = Search(index=index_name)
    s = s.query(final_query)
    s = s.source(includes=["id"])
    s = s.sort("date_created")
    s = s[: settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE]
    if search_after:
        s = s.extra(search_after=search_after)
    return s


def percolate_document(
    document_id: str,
    percolator_index: str,
    document_index: str | None = None,
    document_dict: dict | None = None,
    app_label: str | None = None,
    main_search_after: int | None = None,
    rd_search_after: int | None = None,
    d_search_after: int | None = None,
) -> tuple[Response, Response | None, Response | None]:
    """Percolate a document against a defined Elasticsearch Percolator query.

    :param document_id: The document ID in ES index to be percolated.
    :param percolator_index: The ES percolator index name.
    :param document_index: The ES document index where the document lives.
    :param document_dict: The document dictionary to be percolated.
    :param app_label: The app label and model that belongs to the document
    being percolated.
    :param main_search_after: Optional the ES main percolator query
    search_after param  for deep pagination.
    :param rd_search_after: Optional the ES RECAPDocument percolator query
    search_after param  for deep pagination.
    :param d_search_after: Optional the ES Docket document percolator query
    search_after param  for deep pagination.
    :return: A three-tuple containing the main percolator response, the
    RECAPDocument percolator response (if applicable), and the Docket
    percolator response (if applicable).
    """

    if document_index:
        # If document_index is provided, use it along with the document_id to refer
        # to the document to percolate.
        percolate_query = Q(
            "percolate",
            field="percolator_query",
            index=document_index,
            id=document_id,
        )
    else:
        # Otherwise, use the document_dict to perform the percolation query.
        percolate_query = Q(
            "percolate",
            field="percolator_query",
            document=document_dict,
        )

    exclude_rate_off = Q("term", rate=Alert.OFF)
    final_query = Q(
        "bool",
        must=[percolate_query],
        must_not=[exclude_rate_off],
    )
    s_rd = s_d = None
    s = create_percolator_search_query(
        percolator_index, final_query, search_after=main_search_after
    )
    match app_label:
        case "search.RECAPDocument":
            child_highlight_options, _ = build_highlights_dict(
                SEARCH_RECAP_CHILD_HL_FIELDS, ALERTS_HL_TAG
            )
            parent_highlight_options, _ = build_highlights_dict(
                SEARCH_RECAP_HL_FIELDS, ALERTS_HL_TAG
            )
            child_highlight_options["fields"].update(
                parent_highlight_options["fields"]
            )
            extra_options = {"highlight": child_highlight_options}
            s = s.extra(**extra_options)

            # Prepare filter percolator queries for RECAP and Docket documents.
            recap_document_percolator_index = (
                RECAPDocumentPercolator._index._name
            )
            docket_document_percolator_index = (
                DocketDocumentPercolator._index._name
            )
            if (main_search_after is None) == (rd_search_after is None):
                s_rd = create_percolator_search_query(
                    recap_document_percolator_index,
                    final_query,
                    search_after=rd_search_after,
                )
            if (main_search_after is None) == (d_search_after is None):
                s_d = create_percolator_search_query(
                    docket_document_percolator_index,
                    final_query,
                    search_after=d_search_after,
                )
        case _:
            s = add_es_highlighting(
                s, {"type": SEARCH_TYPES.RECAP}, alerts=True
            )

    s = s.source(excludes=["percolator_query"])

    # Perform the main percolator query, the RECAP query, and the Docket
    # percolator query in a single request.
    multi_search = MultiSearch()
    multi_search = multi_search.add(s)
    if s_rd:
        multi_search = multi_search.add(s_rd)
    if s_d:
        multi_search = multi_search.add(s_d)
    responses = multi_search.execute()

    rd_response = d_response = None
    main_response = responses[0]
    if s_rd:
        rd_response = responses[1]
    if s_d:
        d_response = responses[2]
    return main_response, rd_response, d_response


def fetch_all_search_alerts_results(
    initial_responses: tuple[Response, Response | None, Response | None], *args
) -> tuple[list[Hit], list[Hit], list[Hit]]:
    """Fetches all search alerts results based on a given percolator query and
    the initial responses. It retrieves all the search results that exceed the
    initial batch size by iteratively calling percolate_document method with
    the necessary pagination parameters.
    :param initial_responses: The initial ES Responses tuple.
    :param args: Additional arguments to pass to the percolate_document method.
    :return: A three-tuple containing the main percolator results, the
    RECAPDocument percolator results (if applicable), and the Docket
    percolator results (if applicable).
    """

    all_main_alert_hits = []
    all_rd_alert_hits = []
    all_d_alert_hits = []

    main_response = initial_responses[0]
    all_main_alert_hits.extend(main_response.hits)
    main_total_hits = main_response.hits.total.value
    main_alerts_returned = len(main_response.hits.hits)
    rd_response = d_response = None
    if initial_responses[1]:
        rd_response = initial_responses[1]
        all_rd_alert_hits.extend(rd_response.hits)
    if initial_responses[2]:
        d_response = initial_responses[2]
        all_d_alert_hits.extend(d_response.hits)

    if main_total_hits > settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE:
        alerts_retrieved = main_alerts_returned
        main_search_after = main_response.hits[-1].meta.sort
        rd_search_after = (
            rd_response.hits[-1].meta.sort if rd_response else None
        )
        d_search_after = d_response.hits[-1].meta.sort if d_response else None
        while True:
            search_after_params = {
                "main_search_after": main_search_after,
                "rd_search_after": rd_search_after,
                "d_search_after": d_search_after,
            }
            responses = percolate_document(*args, **search_after_params)
            if not responses[0]:
                break

            all_main_alert_hits.extend(responses[0].hits)
            main_alerts_returned = len(responses[0].hits.hits)
            alerts_retrieved += main_alerts_returned

            if responses[1]:
                all_rd_alert_hits.extend(responses[1].hits)
            if responses[2]:
                all_d_alert_hits.extend(responses[2].hits)
            # Check if all results have been retrieved. If so break the loop
            # Otherwise, increase search_after.
            if (
                alerts_retrieved >= main_total_hits
                or main_alerts_returned == 0
            ):
                break
            else:
                main_search_after = responses[0].hits[-1].meta.sort
                rd_search_after = (
                    responses[1].hits[-1].meta.sort
                    if responses[1] and len(responses[1].hits.hits)
                    else None
                )
                d_search_after = (
                    responses[2].hits[-1].meta.sort
                    if responses[2] and len(responses[2].hits.hits)
                    else None
                )
    return all_main_alert_hits, all_rd_alert_hits, all_d_alert_hits


def override_alert_query(
    alert: Alert, cut_off_date: date | None = None
) -> QueryDict:
    """Override the query parameters for a given alert based on its type and an
     optional cut-off date.

    :param alert: The Alert object for which the query will be overridden.
    :param cut_off_date: An optional date used to set a threshold in the query.
    :return: A QueryDict object containing the modified query parameters.
    """

    qd = QueryDict(alert.query.encode(), mutable=True)
    if alert.alert_type == SEARCH_TYPES.ORAL_ARGUMENT:
        qd["order_by"] = "dateArgued desc"
        if cut_off_date:
            qd["argued_after"] = cut_off_date.strftime("%m/%d/%Y")
    else:
        qd["order_by"] = "dateFiled desc"
        if cut_off_date:
            qd["filed_after"] = cut_off_date.strftime("%m/%d/%Y")

    return qd


def alert_hits_limit_reached(
    alert_pk: int,
    user_pk: int,
    content_type: ContentType | None = None,
    object_id: int | None = None,
    child_document: bool = False,
) -> bool:
    """Check if the alert hits limit has been reached for a specific alert-user
     combination.

    :param alert_pk: The alert_id.
    :param user_pk: The user_id.
    :param content_type: The related content_type.
    :param object_id: The related object_id.
    :param child_document: True if the document to schedule is a child document.
    :return: True if the limit has been reached, otherwise False.
    """

    if child_document:
        # To limit child hits in case, count ScheduledAlertHits related to the
        # alert, user and parent document.
        hits_count = ScheduledAlertHit.objects.filter(
            alert_id=alert_pk,
            user_id=user_pk,
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
            content_type=content_type,
            object_id=object_id,
        ).count()
        hits_limit = settings.RECAP_CHILD_HITS_PER_RESULT + 1
    else:
        # To limit hits in an alert count ScheduledAlertHits related to the
        # alert and user.
        hits_count = (
            ScheduledAlertHit.objects.filter(
                alert_id=alert_pk,
                user_id=user_pk,
                hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
                content_type=content_type,
            )
            .values("object_id")
            .distinct()
        ).count()
        hits_limit = settings.SCHEDULED_ALERT_HITS_LIMIT

    if hits_count >= hits_limit:
        if child_document:
            logger.info(
                f"Skipping child hit for Alert ID: {alert_pk} and object_id "
                f"{object_id}, there are {hits_count} child hits stored for this alert-instance."
            )
        else:
            logger.info(
                f"Skipping hit for Alert ID: {alert_pk}, there are {hits_count} "
                f"hits stored for this alert."
            )
        return True
    return False


def recap_document_hl_matched(rd_hit: Hit) -> bool:
    """Determine whether HL matched a RECAPDocument text field.

    :param rd_hit: The ES hit.
    :return: True if the hit matched a RECAPDocument field. Otherwise, False.
    """

    matched_rd_hl: set[str] = set()
    rd_hl_fields = set(SEARCH_RECAP_CHILD_HL_FIELDS.keys())
    if hasattr(rd_hit, "highlight"):
        highlights = rd_hit.highlight.to_dict()
        matched_rd_hl.update(
            hl_key
            for hl_key, hl_value in highlights.items()
            for hl in hl_value
            if f"<{ALERTS_HL_TAG}>" in hl
        )
    if matched_rd_hl and matched_rd_hl.issubset(rd_hl_fields):
        return True
    return False


def get_alerts_set_prefix() -> str:
    """Simple tool for getting the prefix for the alert hits set.
    Useful for avoiding test collisions.
    """
    return "alert_hits"


def make_alert_set_key(alert_id: int, document_type: str) -> str:
    """Generate a Redis key for storing alert hits.

    :param alert_id: The ID of the alert.
    :param document_type: The type of document associated with the alert.
    :return: A Redis key string in the format "alert_hits:{alert_id}.{document_type}".
    """
    return f"{get_alerts_set_prefix()}:{alert_id}.{document_type}"


def add_document_hit_to_alert_set(
    r: Redis, alert_id: int, document_type: str, document_id: int
) -> None:
    """Add a document ID to the Redis SET associated with an alert ID.

    :param r: Redis client instance.
    :param alert_id: The alert identifier.
    :param document_type: The type of document associated with the alert.
    :param document_id: The docket identifier to add.
    :return: None
    """
    alert_key = make_alert_set_key(alert_id, document_type)
    r.sadd(alert_key, document_id)


def has_document_alert_hit_been_triggered(
    r: Redis, alert_id: int, document_type: str, document_id: int
) -> bool:
    """Check if a document ID is a member of the Redis SET associated with an
     alert ID.

    :param r: Redis client instance.
    :param alert_id: The alert identifier.
    :param document_type: The type of document associated with the alert.
    :param document_id: The docket identifier to check.
    :return: True if the docket ID is a member of the set, False otherwise.
    """
    alert_key = make_alert_set_key(alert_id, document_type)
    return r.sismember(alert_key, document_id)


def build_plain_percolator_query(cd: CleanData) -> Query:
    """Build a plain query based on the provided clean data for its use in the
    Percolator

    :param cd: The query CleanedData.
    :return: An ES Query object representing the built query.
    """

    plain_query = []
    match cd["type"]:
        case (
            SEARCH_TYPES.RECAP
            | SEARCH_TYPES.DOCKETS
            | SEARCH_TYPES.RECAP_DOCUMENT
        ):
            text_fields = SEARCH_RECAP_CHILD_QUERY_FIELDS.copy()
            text_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "description",
                        # Docket Fields
                        "docketNumber",
                        "caseName",
                    ],
                )
            )
            child_filters = build_has_child_filters(cd)
            parent_filters = build_join_es_filters(cd)
            parent_filters.extend(child_filters)

            string_query = build_fulltext_query(
                text_fields, cd.get("q", ""), only_queries=True
            )

            match parent_filters, string_query:
                case [], []:
                    pass
                case [], _:
                    plain_query = Q(
                        "bool",
                        should=string_query,
                        minimum_should_match=1,
                    )
                case _, []:
                    plain_query = Q(
                        "bool",
                        filter=parent_filters,
                    )
                case _, _:
                    plain_query = Q(
                        "bool",
                        filter=parent_filters,
                        should=string_query,
                        minimum_should_match=1,
                    )

    return plain_query


def transform_percolator_child_document(
    es_document: ESDictDocument, hit_meta: dict[str, Any]
) -> None:
    """Transform the given ES document by adding a child document with
    highlights.

    :param es_document: The ES document to be transformed.
    :param hit_meta: The hit meta from the percolator hit, containing highlights
    :return: None, document is modified in place.
    """

    child_document = copy.deepcopy(es_document)
    if hasattr(hit_meta, "highlight"):
        merge_highlights_into_result(
            hit_meta.highlight.to_dict(),
            child_document,
        )
    es_document["child_docs"] = [child_document]


def include_recap_document_hit(
    alert_id: int, recap_document_hits: list[int], docket_hits: list[int]
) -> bool:
    """Determine if an alert should include the percolated RECAP document
     based on its presence in the given lists:

    If an alert hit reached this method it was found in the main percolator request.
    So we just need to confirm the following conditions to avoid including a
    RECAPDocument into a Docket-only query alert.

    alert_in_docket_hits     alert_in_rd_hits   Output
        False                    False           True  AND Cross-object queries
        False                    True            True  RD-only queries.
        True                     False           False Docket-only queries.
        True                     True            True  OR Cross-object queries

    :param alert_id: The ID of the alert to check.
    :param recap_document_hits: A list RECAPDocument alert hits IDs.
    :param docket_hits:  A list Docket alert hits IDs.
    :return: True if the alert should include a RECAP document hit, otherwise False.
    """

    alert_in_rd_hits = alert_id in recap_document_hits
    alert_in_docket_hits = alert_id in docket_hits
    if not alert_in_docket_hits and not alert_in_rd_hits:
        return True
    elif not alert_in_docket_hits and alert_in_rd_hits:
        return True
    elif alert_in_docket_hits and not alert_in_rd_hits:
        return False
    elif alert_in_docket_hits and alert_in_rd_hits:
        return True
    return False


def avoid_indexing_auxiliary_alert(
    index_name: str, alert_query: QueryDict
) -> bool:
    """Determine if an alert should be avoided for indexing in the auxiliary
    percolator index based on the index_name and query filters.

    :param index_name: The name of the Elasticsearch index to check.
    :param alert_query: QueryDict containing the alert query parameters.
    :return: True if the alert should be avoided for indexing, otherwise False.
    """

    if index_name == DocketDocumentPercolator.__name__:
        # Avoid indexing alerts that contains RECAPDocument filters into the
        # DocketDocumentPercolator, otherwise it'll throw a parsing error.
        for rd_filter in recap_document_filters:
            if alert_query.get(rd_filter, ""):
                return True

    if index_name == RECAPDocumentPercolator.__name__:
        # Avoid indexing alerts that contains Docket filters into the
        # RECAPDocumentPercolator, otherwise it'll throw a parsing error.
        for d_filter in docket_document_filters:
            if alert_query.get(d_filter, ""):
                return True
    return False


def prepare_percolator_content(
    app_label: str, document_id: str, document_content: ESDictDocument
) -> tuple[str, str | None, ESDictDocument]:
    """Prepare percolator content for different according to the app_label.

    It returns the percolator index name and the ES document index where the
    document lives. For RECAPDocument, instead of an ES document index, the
    document to percolate is prepared based on the ESRECAPDocumentPlain mapping
    that includes docket fields like parties.

    :param app_label: The label of the app to determine the percolator and
    document indices.
    :param document_id: The ID of the document to fetch and prepare, used for
    RECAP documents.
    :param document_content: The initial content of the document, which may be
    modified for RECAPDocument.
    :return: A three tuple containing the percolator index name, document index
    name, and the document_content.
    """

    es_document_index = None
    match app_label:
        case "audio.Audio":
            percolator_index = AudioPercolator._index._name
            es_document_index = AudioDocument._index._name
        case "search.Docket":
            percolator_index = RECAPPercolator._index._name
            es_document_index = DocketDocument._index._name
        case "search.RECAPDocument":
            percolator_index = RECAPPercolator._index._name
            model = apps.get_model(app_label)
            rd = model.objects.get(pk=document_id)
            document_content = ESRECAPDocumentPlain().prepare(rd)
            # Remove docket_child to avoid document parsing errors.
            del document_content["docket_child"]
        case _:
            raise NotImplementedError(
                "Percolator search alerts not supported for %s", app_label
            )

    return percolator_index, es_document_index, document_content
