import logging
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta, timezone
from itertools import batched, chain
from typing import Any, Dict, List, Set, TypedDict, Union

import eyecite
from dateutil import parser
from dateutil.rrule import DAILY, rrule
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import intcomma, ordinal
from django.db.models import F
from django.db.models.constants import LOOKUP_SEP
from django.urls import resolve
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django_ratelimit.core import get_header
from eyecite.tokenizers import HyperscanTokenizer
from requests import Response
from rest_framework import serializers
from rest_framework.exceptions import Throttled
from rest_framework.metadata import SimpleMetadata
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.request import clone_request
from rest_framework.throttling import UserRateThrottle
from rest_framework_filters import FilterSet, RelatedFilter
from rest_framework_filters.backends import RestFrameworkFilterBackend
from rest_framework_filters.filterset import related

from cl.api.models import (
    WEBHOOK_EVENT_STATUS,
    Webhook,
    WebhookEvent,
    WebhookVersions,
)
from cl.citations.utils import filter_out_non_case_law_and_non_valid_citations
from cl.lib.redis_utils import get_redis_interface
from cl.stats.models import Event
from cl.stats.utils import MILESTONES_FLAT, get_milestone_range
from cl.users.tasks import notify_failing_webhook

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")
BOOLEAN_LOOKUPS = ["exact"]
DATETIME_LOOKUPS = [
    "exact",
    "gte",
    "gt",
    "lte",
    "lt",
    "range",
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
]
DATE_LOOKUPS = DATETIME_LOOKUPS[:-3]
INTEGER_LOOKUPS = ["exact", "gte", "gt", "lte", "lt", "range"]
BASIC_TEXT_LOOKUPS = [
    "exact",
    "iexact",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
]
ALL_TEXT_LOOKUPS = BASIC_TEXT_LOOKUPS + ["contains", "icontains"]

logger = logging.getLogger(__name__)


class HyperlinkedModelSerializerWithId(serializers.HyperlinkedModelSerializer):
    """Extend the HyperlinkedModelSerializer to add IDs as well for the best of
    both worlds.
    """

    id = serializers.ReadOnlyField()


class DisabledHTMLFilterBackend(RestFrameworkFilterBackend):
    """Disable showing filters in the browsable API.

    Ideally, we'd want to show fields in the browsable API, but for related
    objects this loads every object into the HTML and it loads them from the DB
    one query at a time. It's insanity, so it's gotta be disabled globally.
    """

    def to_html(self, request, queryset, view):
        return ""


class FilterManyToManyMixin:
    """
    Mixin for filtering nested many-to-many relationships.

    Provides helper methods to efficiently filter nested querysets when using
    `RelatedFilter` classes in filtersets. This is particularly useful for
    scenarios where you need to filter on attributes of related models through
    many-to-many relationships.

    **Required Properties:**
    - **`join_table_cleanup_mapping`**: A dictionary mapping the field_name
      or custom labels used for `RelatedFilter` fields to the corresponding
      field names in the join table. This mapping is essential for correct
      filtering.
    """

    join_table_cleanup_mapping: dict[str, str] = {}

    def _get_filter_label(self: FilterSet, field_name: str) -> str:
        """
        Maps a filter field name to its corresponding label.

        When defining filters(Declarative or using the `fields` attribute) in a
        filterset, the field name used internally might not directly match the
        the label used in the request. This method helps resolve this
        discrepancy by mapping the given `field_name` to its correct label.

        This is particularly useful for custom filter methods where only the
        field name is available, and obtaining the triggering label is not
        straightforward.

        Args:
            field_name (str): The field name as used within the filterset.

        Returns:
            str: The corresponding label for the given field name.
        """

        FIELD_NAME_LABEL_MAPPING = {
            filter_class.field_name: label
            for label, filter_class in self.filters.items()
        }
        return FIELD_NAME_LABEL_MAPPING[field_name]

    def _clean_join_table_key(self, key: str) -> str:
        """
        Cleans and adjusts a given key for compatibility with prefetch queries.

        This method modifies specific lookups within the `key` to ensure
        correct filtering when used in prefetch queries. It iterates over a
        mapping of URL keys to new keys, replacing instances of URL keys with
        their corresponding new keys.

        Args:
            key (str): The original key to be cleaned.

        Returns:
            str: The cleaned key, adjusted for prefetch query compatibility.
        """
        join_table_key = key
        for url_key, new_key in self.join_table_cleanup_mapping.items():
            join_table_key = join_table_key.replace(url_key, new_key, 1)
        return join_table_key

    def get_filters_for_join_table(self: FilterSet) -> dict[str, Any]:
        """
        Processes request filters for use in a join table query.

        Iterates through the request filters, cleaning and transforming them to
        be suitable for applying filtering conditions to a join table. Returns
        a dictionary containing the filtered criteria to be applied to the join
        table query.

        Args:
            name: The name of label used to trigger the custom filtering method

        Returns:
            dict: A dictionary containing the filtered criteria for the join
            table query.
        """
        filters: dict[str, Any] = {}
        # Iterate over related filtersets
        for related_name, related_filterset in self.related_filtersets.items():
            prefix = f"{related(self, related_name)}{LOOKUP_SEP}"
            # Check if the related filterset has data to apply
            if not any(value.startswith(prefix) for value in self.data):
                # Skip processing if no parameter starts with the prefix
                continue

            # Extract and clean the field name to be used as a filter.
            #
            # We start with the field name from the `filters` dictionary,
            # which is associated with the `related_name`.
            #
            # The `_clean_join_table_key` method is used to ensure
            # compatibility with prefetch queries.  The cleaned field name is
            # then used to  construct a lookup expression that will perform
            # an `IN` query. This approach is efficient for filtering multiple
            # values.
            clean_field_name = self._clean_join_table_key(
                self.filters[related_name].field_name
            )
            lookup_expr = LOOKUP_SEP.join([clean_field_name, "in"])

            # Extract the field name to retrieve values from the subquery.
            #
            # This field is determined by the `to_field_name` attribute of
            # the related filterset's field. If not specified, the default `pk`
            # (primary key) is used.
            #
            # The subquery is constructed using the underlying form's
            # `cleaned_data` to ensure that invalid lookups in the request are
            # gracefully ignored.
            to_field_name = (
                getattr(
                    self.filters[related_name].field, "to_field_name", "pk"
                )
                or "pk"
            )
            subquery = related_filterset.qs.values(to_field_name)

            # Merge the current lookup expression into the existing filter set.
            filters = filters | {lookup_expr: subquery}

        return filters


class NoEmptyFilterSet(FilterSet):
    """A custom filterset to ensure we don't get empty filter parameters."""

    def __init__(
        self, data=None, queryset=None, *, relationship=None, **kwargs
    ):
        # Remove any empty query parameters from the QueryDict. Fixes #2066
        if data:
            # Make a mutable copy so we can tweak it.
            data = data.copy()
            [data.pop(k) for k, v in list(data.items()) if not v]
        super().__init__(
            data=data, queryset=queryset, relationship=relationship, **kwargs
        )


class SimpleMetadataWithFilters(SimpleMetadata):
    def determine_metadata(self, request, view):
        metadata = super().determine_metadata(request, view)
        filters = OrderedDict()
        if not hasattr(view, "filterset_class"):
            # This is the API Root, which is not filtered.
            return metadata

        for (
            filter_name,
            filter_type,
        ) in view.filterset_class.base_filters.items():
            filter_parts = filter_name.split("__")
            filter_name = filter_parts[0]
            attrs = OrderedDict()

            # Type
            attrs["type"] = filter_type.__class__.__name__

            # Lookup fields
            if len(filter_parts) > 1:
                # Has a lookup type (__gt, __lt, etc.)
                lookup_type = filter_parts[1]
                if filters.get(filter_name) is not None:
                    # We've done a filter with this name previously, just
                    # append the value.
                    attrs["lookup_types"] = filters[filter_name][
                        "lookup_types"
                    ]
                    attrs["lookup_types"].append(lookup_type)
                else:
                    attrs["lookup_types"] = [lookup_type]
            else:
                # Exact match or RelatedFilter
                if isinstance(filter_type, RelatedFilter):
                    model_name = (
                        filter_type.filterset.Meta.model._meta.verbose_name_plural.title()
                    )
                    attrs["lookup_types"] = (
                        f"See available filters for '{model_name}'"
                    )
                else:
                    attrs["lookup_types"] = ["exact"]

            # Do choices
            choices = filter_type.extra.get("choices", False)
            if choices:
                attrs["choices"] = [
                    {
                        "value": choice_value,
                        "display_name": force_str(
                            choice_name, strings_only=True
                        ),
                    }
                    for choice_value, choice_name in choices
                ]

            # Wrap up.
            filters[filter_name] = attrs

        metadata["filters"] = filters

        if hasattr(view, "ordering_fields"):
            metadata["ordering"] = view.ordering_fields
        return metadata

    def determine_actions(self, request, view):
        """Simple override to always show the field information even for people
        that don't have POST access.

        Fixes issue #732.
        """
        actions = {}
        for method in {"PUT", "POST"} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            if method == "PUT" and hasattr(view, "get_object"):
                view.get_object()
            serializer = view.get_serializer()
            actions[method] = self.get_serializer_info(serializer)
            view.request = request

        return actions


def get_logging_prefix(api_version: str) -> str:
    """Simple tool for getting the prefix for logging API requests. Useful for
    mocking the logger.
    """
    return f"api:{api_version}"


class LoggingMixin:
    """Log requests to Redis

    This draws inspiration from the code that can be found at:
      https://github.com/aschn/drf-tracking/blob/master/rest_framework_tracking/mixins.py

    The big distinctions, however, are that this code uses Redis for greater
    speed, and that it logs significantly less information.

    We want to know:
     - How many queries in last X days, total?
     - How many queries ever, total?
     - How many queries total made by user X?
     - How many queries per day made by user X?
    """

    milestones = get_milestone_range("SM", "XXXL")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)

        # For logging the timing in self.finalize_response
        self.requested_at = now()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(
            request, response, *args, **kwargs
        )

        if not response.exception:
            # Don't log things like 401, 403, etc.,
            # noinspection PyBroadException
            try:
                results = self._log_request(request)
                self._handle_events(results, request.user, request.version)
            except Exception as e:
                logger.exception(
                    "Unable to log API response timing info: %s", e
                )
        return response

    def _get_response_ms(self) -> int:
        """
        Get the duration of the request response cycle in milliseconds.
        In case of negative duration 0 is returned.
        """
        response_timedelta = now() - self.requested_at
        response_ms = int(response_timedelta.total_seconds() * 1000)

        return max(response_ms, 0)

    def _log_request(self, request):
        d = date.today().isoformat()
        user = request.user
        client_ip = get_header(request, "CloudFront-Viewer-Address").split(
            ":"
        )[0]
        endpoint = resolve(request.path_info).url_name
        response_ms = self._get_response_ms()

        r = get_redis_interface("STATS")
        pipe = r.pipeline()
        api_prefix = get_logging_prefix(request.version)

        # Global and daily tallies for all URLs.
        pipe.incr(f"{api_prefix}.count")
        pipe.incr(f"{api_prefix}.d:{d}.count")
        pipe.incr(f"{api_prefix}.timing", response_ms)
        pipe.incr(f"{api_prefix}.d:{d}.timing", response_ms)

        # Use a sorted set to store the user stats, with the score representing
        # the number of queries the user made total or on a given day.
        user_pk = user.pk or "AnonymousUser"
        pipe.zincrby(f"{api_prefix}.user.counts", 1, user_pk)
        pipe.zincrby(f"{api_prefix}.user.d:{d}.counts", 1, user_pk)

        # Use a hash to store a per-day map between IP addresses and user pks
        # Get a user pk with: `hget api:v3.d:2022-05-18.ip_map 172.19.0.1`
        if client_ip is not None:
            ip_key = f"{api_prefix}.d:{d}.ip_map"
            pipe.hset(ip_key, client_ip, user_pk)
            pipe.expire(ip_key, 60 * 60 * 24 * 14)  # Two weeks

        # Use a sorted set to store all the endpoints with score representing
        # the number of queries the endpoint received total or on a given day.
        pipe.zincrby(f"{api_prefix}.endpoint.counts", 1, endpoint)
        pipe.zincrby(f"{api_prefix}.endpoint.d:{d}.counts", 1, endpoint)

        # We create a per-day key in redis for timings. Inside the key we have
        # members for every endpoint, with score of the total time. So to get
        # the average for an endpoint you need to get the number of requests
        # and the total time for the endpoint and divide.
        timing_key = f"{api_prefix}.endpoint.d:{d}.timings"
        pipe.zincrby(timing_key, response_ms, endpoint)

        results = pipe.execute()
        return results

    def _handle_events(self, results, user, api_version):
        total_count = results[0]
        user_count = results[4]

        if total_count in MILESTONES_FLAT:
            Event.objects.create(
                description=f"API {api_version} has logged {total_count} total requests."
            )
        if user.is_authenticated:
            if user_count in self.milestones:
                Event.objects.create(
                    description="User '%s' has placed their %s API %s request."
                    % (
                        user.username,
                        intcomma(ordinal(user_count)),
                        api_version,
                    ),
                    user=user,
                )


class CacheListMixin:
    """Cache listed results"""

    @method_decorator(cache_page(60))
    # Ensure that permissions are maintained and not cached!
    @method_decorator(vary_on_headers("Cookie", "Authorization"))
    def list(self, *args, **kwargs):
        return super().list(*args, **kwargs)


class ExceptionalUserRateThrottle(UserRateThrottle):
    def allow_request(self, request, view):
        """
        Give special access to a few special accounts.

        Mirrors code in super class with minor tweaks.
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Adjust if user has special privileges.
        override_rate = settings.REST_FRAMEWORK["OVERRIDE_THROTTLE_RATES"].get(
            request.user.username, None
        )
        if override_rate is not None:
            self.num_requests, self.duration = self.parse_rate(override_rate)

        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()


class CitationCountRateThrottle(ExceptionalUserRateThrottle):
    """
    Limits the rate of API calls that may be made by users based on the
    number of citations they try to look up.
    """

    def get_citation_count_from_request(self, request, view) -> int:
        """
        Gets the number of citations from a request.

        This helper method retrieves the number of citations from a request
        object. It first validates the data using the `validate_request_data`
        method. If valid, it extracts the citations list, stores it in the
        view instance and it returns the number of citations in the list.

        Returns:
            int: The number of citations as an integer.
        """
        validated_data = view.validate_request_data(request)
        text = validated_data.get("text", None)
        if not text:
            # Since the 'text' key is missing from the request, the user is
            # likely trying to retrieve opinions using a reporter, volume,
            # and page combination. This approach allows looking up one
            # citation at a time.
            return 1

        citation_objs = filter_out_non_case_law_and_non_valid_citations(
            eyecite.get_citations(text, tokenizer=HYPERSCAN_TOKENIZER)
        )
        view.citation_list = citation_objs
        return len(citation_objs)

    def get_cache_key_for_citations(self, request, view):
        return self.cache_format % {
            "scope": "citations",
            "ident": request.user.pk,
        }

    def get_citations_rate(self, request):
        """
        Checks the settings for a custom citations API rate limit.

        If the authenticated user has a custom rate limit set in the settings,
        it returns that value. Otherwise, it returns the default rate limit.

        Args:
            request: The request object with the user's data.
        """
        default_rate = self.THROTTLE_RATES["citations"]
        custom_rate = settings.REST_FRAMEWORK[
            "CITATION_LOOKUP_OVERRIDE_THROTTLE_RATES"
        ].get(request.user.username, None)
        return custom_rate or default_rate

    def throttle_request_by_citation_count(self, request, view):
        max_num_citations, _ = self.parse_rate(
            self.get_citations_rate(request)
        )

        self.key = self.get_cache_key_for_citations(request, view)
        self.history = self.cache.get(self.key, [])
        self.request_timestamp = self.timer()

        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1][-1] <= self.request_timestamp:
            self.history.pop()

        citations_in_history = sum(
            citation_count for citation_count, timestamps in self.history
        )

        if citations_in_history >= max_num_citations:
            self.throttle_request(request)

        self.save_citation_count(request, view)

    def save_citation_count(self, request, view):
        """
        Inserts the number of citations and the expiration time along with
        the key into the cache.
        """
        citation_count = self.get_citation_count_from_request(request, view)
        if not citation_count:
            return

        max_num_citations, duration = self.parse_rate(
            self.get_citations_rate(request)
        )
        expiration = (
            citation_count * (duration / max_num_citations)
            if citation_count > max_num_citations
            else duration
        )
        self.history.insert(
            0,
            [
                citation_count,
                self.request_timestamp + expiration,
            ],
        )

        self.cache.set(self.key, self.history, expiration)

    def allow_request(self, request, view):
        self.throttle_request_by_citation_count(request, view)
        return super().allow_request(request, view)

    def throttle_request(self, request):
        """
        This helper iterates through the request history in reverse
        chronological order to calculate the soonest time a new request can be
        made and raises the `Throttled` exception with the details.

        The exception includes details about the throttling:

        - `error_message`: A message indicating the request was throttled.
        - `wait_until`: An ISO 8601 formatted string representing the soonest
                    time the next request can be made without throttling.

        Args:
            request: The request object to be throttled.

        Raises:
            Throttled: The exception includes details about the throttling.
        """
        rate = self.get_citations_rate(request)
        max_num_citations, _ = self.parse_rate(rate)
        soonest_time = None
        for idx in reversed(range(len(self.history))):
            remaining_citation = sum(
                citation_count for citation_count, _ in self.history[:idx]
            )
            if remaining_citation < max_num_citations or not idx:
                datetime_obj = datetime.fromtimestamp(
                    self.history[idx][-1], timezone.utc
                )
                soonest_time = datetime_obj.isoformat()
                break

        raise Throttled(
            detail={
                "error_message": f"Too many requests (allowed rate: {rate}).",
                "wait_until": soonest_time,
            }
        )


class RECAPUsersReadOnly(DjangoModelPermissions):
    """Provides access to users with the right permissions.

    Such users must have the has_recap_api_access flag set on their account for
    this object type.
    """

    perms_map = {
        "GET": ["%(app_label)s.has_recap_api_access"],
        "OPTIONS": ["%(app_label)s.has_recap_api_access"],
        "HEAD": ["%(app_label)s.has_recap_api_access"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class RECAPUploaders(DjangoModelPermissions):
    """Provides some users upload permissions in RECAP

    Such users must have the has_recap_upload_access flag set on their account
    """

    perms_map = {
        "GET": ["%(app_label)s.has_recap_upload_access"],
        "OPTIONS": ["%(app_label)s.has_recap_upload_access"],
        "HEAD": ["%(app_label)s.has_recap_upload_access"],
        "POST": ["%(app_label)s.has_recap_upload_access"],
        "PUT": ["%(app_label)s.has_recap_upload_access"],
        "PATCH": ["%(app_label)s.has_recap_upload_access"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class EmailProcessingQueueAPIUsers(DjangoModelPermissions):
    perms_map = {
        "POST": ["%(app_label)s.has_recap_upload_access"],
        "GET": ["%(app_label)s.has_recap_upload_access"],
    }


def make_date_str_list(
    start: Union[str, datetime],
    end: Union[str, datetime],
) -> List[str]:
    """Make a list of date strings for a date span

    :param start: The beginning date, as a string or datetime object
    :param end: The end date, as a string or datetime object
    :returns: A list of dates in the ISO-8601 format
    """
    if isinstance(start, str):
        start = parser.parse(start, fuzzy=False)
    if isinstance(end, str):
        end = parser.parse(end, fuzzy=False)
    return [
        d.date().isoformat() for d in rrule(DAILY, dtstart=start, until=end)
    ]


def invert_user_logs(
    start: Union[str, datetime],
    end: Union[str, datetime],
    add_usernames: bool = True,
) -> Dict[str, Dict[str, int]]:
    """Aggregate API usage statistics per user over a date range.

    - Anonymous users are aggregated under the key 'AnonymousUser'.
    - Both v3 and v4 API counts are combined in the results.

    :param start: Beginning date (inclusive) for the query range
    :param end: End date (inclusive) for the query range
    :param add_usernames: If True, replaces user IDs with usernames as keys.
        When False, uses only user IDs as keys.

    :return: Dictionary mapping user identifiers (usernames if `add_usernames=True`,
        otherwise user IDs) to their daily API usage counts and totals.
        Inner dictionaries are ordered by date. Only dates with usage are included.
    """
    r = get_redis_interface("STATS")
    pipe = r.pipeline()

    dates = make_date_str_list(start, end)
    versions = ["v3", "v4"]
    for d in dates:
        for version in versions:
            pipe.zrange(
                f"api:{version}.user.d:{d}.counts",
                0,
                -1,
                withscores=True,
            )

    # results contains alternating v3/v4 API usage data for each date queried.
    # For example, if querying 2023-01-01 to 2023-01-02, results might look like:
    # [
    #     # 2023-01-01 v3 data: [(user_id, count), ...]
    #     [("1", 100.0), ("2", 50.0)],
    #     # 2023-01-01 v4 data
    #     [("1", 50.0), ("2", 25.0)],
    #     # 2023-01-02 v3 data
    #     [("1", 200.0), ("2", 100.0)],
    #     # 2023-01-02 v4 data
    #     [("1", 100.0), ("2", 50.0)]
    # ]
    # We zip this with dates to combine v3/v4 counts per user per day
    results = pipe.execute()

    out: defaultdict = defaultdict(dict)

    def update_user_counts(_user_id, _count, _date):
        user_is_anonymous = _user_id == "None" or _user_id == "AnonymousUser"
        _user_id = "AnonymousUser" if user_is_anonymous else int(_user_id)
        _count = int(_count)
        out.setdefault(_user_id, OrderedDict())
        out[_user_id].setdefault(_date, 0)
        out[_user_id][_date] += _count
        out[_user_id].setdefault("total", 0)
        out[_user_id]["total"] += _count

    for d, api_usage in zip(dates, batched(results, len(versions))):
        for user_id, count in chain(*api_usage):
            update_user_counts(user_id, count, d)

    # Sort the values
    for k, v in out.items():
        out[k] = OrderedDict(sorted(v.items(), key=lambda t: t[0]))

    if not add_usernames:
        return out

    # Add usernames as alternate keys for every value possible.
    user_keyed_out = {}
    for k, v in out.items():
        try:
            user = User.objects.get(pk=k)
        except (User.DoesNotExist, ValueError):
            user_keyed_out[k] = v
        else:
            user_keyed_out[user.username] = v

    return user_keyed_out


def get_user_ids_for_date_range(
    start: Union[str, datetime],
    end: Union[str, datetime],
) -> Set[int]:
    """Get a list of user IDs that used the API during a span of time

    :param start: The beginning of when you want to find users. A str to be
    interpreted by dateparser.
    :param end: The end of when you want to find users.  A str to be
    interpreted by dateparser.
    :return Set of user IDs during a time period. Will not contain anonymous
    users.
    """
    r = get_redis_interface("STATS")
    pipe = r.pipeline()

    date_strs = make_date_str_list(start, end)
    for d in date_strs:
        pipe.zrange(f"api:v3.user.d:{d}.counts", 0, -1)

    results: list = pipe.execute()
    result_set: set = set().union(*results)
    return {int(i) for i in result_set if i.isdigit()}


def get_count_for_endpoint(endpoint: str, start: str, end: str) -> int:
    """Get the count of hits for an endpoint by name, during a date range

    :param endpoint: The endpoint to get the count for. Typically something
    like 'docket-list' or 'docket-detail'
    :param start: The beginning date (inclusive) you want the results for.
    :param end: The end date (inclusive) you want the results for.
    :return int: The count for that endpoint
    """
    r = get_redis_interface("STATS")
    pipe = r.pipeline()

    dates = make_date_str_list(start, end)
    for d in dates:
        pipe.zscore(f"api:v3.endpoint.d:{d}.counts", endpoint)
    results = pipe.execute()
    return sum(r for r in results if r)


def get_avg_ms_for_endpoint(endpoint: str, d: datetime) -> float:
    """

    :param endpoint: The endpoint to get the average timing for. Typically
    something like 'docket-list' or 'docket-detail'
    :param d: The date to get the timing for (a date object)
    :return: The average number of ms that endpoint used to serve requests on
    that day.
    """
    d_str = d.isoformat()
    r = get_redis_interface("STATS")
    pipe = r.pipeline()
    pipe.zscore(f"api:v3.endpoint.d:{d_str}.timings", endpoint)
    pipe.zscore(f"api:v3.endpoint.d:{d_str}.counts", endpoint)
    results = pipe.execute()

    return results[0] / results[1]


def get_next_webhook_retry_date(retry_counter: int) -> datetime:
    """Returns the next retry datetime to schedule a webhook retry based on its
    current retry counter.

    The next retry date is computed based to meet an exponential backoff with a
    starting multiplier of three.

      Retry counter | New Delay
      -------------+------------
            1      |     0:03
            2      |     0:09
            3      |     0:27
            4      |     1:21
            5      |     4:03
            6      |     12:09
            7      |     36:27


    The total elapsed time might vary for each webhook event depending on when
    the retry is executed since the retry method is going to be executed every
    minute. On average the total elapsed time in the 7th retry would be 54
    hours and 39 minutes.

    :param retry_counter: The current retry_counter used to compute the next
    retry date.
    :return datatime: The next retry datetime.
    """

    INITIAL_TIME = 3  # minutes
    # Update new_next_retry_date exponentially
    new_next_retry_date = now() + timedelta(
        minutes=pow(INITIAL_TIME, retry_counter + 1)
    )
    return new_next_retry_date


WEBHOOK_MAX_RETRY_COUNTER = 7


def check_webhook_failure_count_and_notify(
    webhook_event: WebhookEvent,
) -> None:
    """Check if a Webhook needs to be disabled and/or send a notification about
     a failing webhook event. Only email failing webhook notifications based on
     the oldest active ENQUEUED_RETRY WebhookEvent, avoiding sending
     notifications for every failing webhook event.

    :param webhook_event: The related WebhookEvent to check.
    :return: None
    """

    # Send failing webhook events notifications for only some of the retries
    notify_on = {
        0: False,
        1: True,  # Send first webhook failing notification
        2: False,
        3: False,
        4: False,
        5: True,  # Send second webhook failing notification
        6: False,
        7: True,  # Send webhook disabled notification
    }
    webhook = webhook_event.webhook
    if not webhook.enabled or webhook_event.debug:
        return

    webhook.failure_count = F("failure_count") + 1
    update_fields = ["failure_count"]

    current_try_counter = webhook_event.retry_counter
    notify = notify_on[current_try_counter]
    if notify:
        oldest_enqueued_for_retry = WebhookEvent.objects.filter(
            webhook=webhook_event.webhook,
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            debug=False,
        ).earliest("date_created")
        if current_try_counter >= WEBHOOK_MAX_RETRY_COUNTER:
            webhook.enabled = False
            update_fields.append("enabled")
            update_fields.append("date_modified")
            # If the parent webhook is disabled mark all current ENQUEUED_RETRY
            # events as ENDPOINT_DISABLED
            WebhookEvent.objects.filter(
                webhook=webhook_event.webhook,
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                debug=False,
            ).update(
                event_status=WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
                date_modified=now(),
            )
        if oldest_enqueued_for_retry.pk == webhook_event.pk:
            failure_counter = current_try_counter + 1
            notify_failing_webhook.delay(
                webhook_event.pk, failure_counter, webhook.enabled
            )

    # Save webhook and avoid emailing admins via signal in cl.users.signals
    webhook.save(update_fields=update_fields)


def update_webhook_event_after_request(
    webhook_event: WebhookEvent,
    response: Response | None = None,
    error: str | None = "",
) -> None:
    """Update the webhook event after sending the POST request. If the webhook
    event fails, increase the retry counter, next retry date and increase its
    parent webhook failure count. If the webhook event reaches the max retry
    counter marks it as Failed. If there is no error marks it as Successful.

    :param webhook_event: The WebhookEvent to update.
    :param response: Optional in case we receive a requests Response object, to
    update the WebhookEvent accordingly.
    :param error: Optional, if we don't receive a request Response we'll
    receive an error to log it.
    :return: None
    """

    failed_request = False
    data = ""
    status_code = None
    if response is not None:
        # The webhook response is consumed as a stream to avoid blocking the
        # process and overflowing memory on huge responses. We only read and
        # store the first 4KB
        for chunk in response.iter_content(1024 * 4, decode_unicode=True):
            data = chunk
            break
        response.close()
        status_code = response.status_code
        # If the response status code is not 2xx. It's considered a failed
        # attempt, and it'll be enqueued for retry.
        if not 200 <= response.status_code < 300:
            failed_request = True
    webhook_event.status_code = status_code
    webhook_event.response = data

    if failed_request or error:
        if error is None:
            error = ""
        webhook_event.error_message = error
        check_webhook_failure_count_and_notify(webhook_event)
        if webhook_event.retry_counter >= WEBHOOK_MAX_RETRY_COUNTER:
            # If the webhook has reached the max retry counter, mark as failed
            webhook_event.event_status = WEBHOOK_EVENT_STATUS.FAILED
            webhook_event.retry_counter = F("retry_counter") + 1
            webhook_event.save()
            return

        webhook_event.next_retry_date = get_next_webhook_retry_date(
            webhook_event.retry_counter
        )
        webhook_event.retry_counter = F("retry_counter") + 1
        webhook_event.event_status = WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY
        if webhook_event.debug:
            # Test events are not enqueued for retry.
            webhook_event.event_status = WEBHOOK_EVENT_STATUS.FAILED
    else:
        webhook_event.event_status = WEBHOOK_EVENT_STATUS.SUCCESSFUL
        if not webhook_event.debug:
            # Only log successful webhook events and not debug.
            results = log_webhook_event(webhook_event.webhook.user.pk)
            handle_webhook_events(results, webhook_event.webhook.user)
    webhook_event.save()


class WebhookKeyType(TypedDict):
    event_type: int
    version: int
    date_created: str | None
    deprecation_date: str | None


def get_webhook_deprecation_date(webhook_deprecation_date: str) -> str:
    """Convert a webhook deprecation date string to ISO-8601 format with
     UTC timezone.

    :param webhook_deprecation_date: The deprecation date as a string in
    "YYYY-MM-DD" format.
    :return: The ISO-8601 formatted date string with UTC timezone.
    """

    deprecation_date = (
        datetime.strptime(webhook_deprecation_date, "%Y-%m-%d")
        .replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        .isoformat()
    )
    return deprecation_date


def generate_webhook_key_content(webhook: Webhook) -> WebhookKeyType:
    """Generate a dictionary representing the content for the webhook key.

    :param webhook: The Webhook instance.
    :return: A dictionary containing webhook details, event type, version,
    creation date in ISO format, and deprecation date according webhook version.
    """

    deprecation_date: str | None = None
    match webhook.version:
        case WebhookVersions.v1:
            deprecation_date = get_webhook_deprecation_date(
                settings.WEBHOOK_V1_DEPRECATION_DATE  # type: ignore
            )
        case WebhookVersions.v2:
            deprecation_date = None

    return {
        "event_type": webhook.event_type,
        "version": webhook.version,
        "date_created": webhook.date_created.isoformat(),
        "deprecation_date": deprecation_date,
    }


def get_webhook_logging_prefix() -> str:
    """Simple tool for getting the prefix for logging webhook requests.
    Useful for mocking the logger.
    """
    return "webhook:v1"


def log_webhook_event(webhook_user_id: int) -> list[int | float]:
    """Log a successful webhook event to redis.

    :param webhook_user_id: The webhook user id
    :return: A list of successful webhook events' global count and the user's
    webhook count.
    """

    r = get_redis_interface("STATS")
    pipe = r.pipeline()
    webhook_prefix = get_webhook_logging_prefix()

    # Global tallies for all webhook endpoints and users.
    pipe.incr(f"{webhook_prefix}.count")

    # Use a sorted set to store the user stats, with the score representing
    # the number of successful webhook request the user made in total.
    pipe.zincrby(f"{webhook_prefix}.user.counts", 1, webhook_user_id)

    results = pipe.execute()
    return results


def handle_webhook_events(results: list[int | float], user: User) -> None:
    """Create global and user tracking events if a webhook milestone is
    reached.

    :param results: A list of successful webhook events' global count and the
    user's webhook count.
    :param user: The webhook user
    :return: None
    """
    total_count = results[0]
    user_count = results[1]

    if total_count in MILESTONES_FLAT:
        Event.objects.create(
            description=f"Webhooks have logged {total_count} total successful events."
        )

    if user_count in MILESTONES_FLAT:
        Event.objects.create(
            description=f"User '{user.username}' has placed their "
            f"{intcomma(ordinal(user_count))} webhook event.",
            user=user,
        )
