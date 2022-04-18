import json
import logging
import os
from collections import OrderedDict, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Set, Union

from dateutil import parser
from dateutil.rrule import DAILY, rrule
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import intcomma, ordinal
from django.core.mail import send_mail
from django.db import connections
from django.urls import resolve
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework import serializers
from rest_framework.metadata import SimpleMetadata
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.request import clone_request
from rest_framework.throttling import UserRateThrottle
from rest_framework_filters import RelatedFilter
from rest_framework_filters.backends import RestFrameworkFilterBackend

from cl.lib.db_tools import fetchall_as_dict
from cl.lib.redis_utils import make_redis_interface
from cl.stats.models import Event
from cl.stats.utils import MILESTONES_FLAT, get_milestone_range

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


class SimpleMetadataWithFilters(SimpleMetadata):
    def determine_metadata(self, request, view):
        metadata = super(SimpleMetadataWithFilters, self).determine_metadata(
            request, view
        )
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
                    attrs[
                        "lookup_types"
                    ] = f"See available filters for '{model_name}'"
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


class LoggingMixin(object):
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
        super(LoggingMixin, self).initial(request, *args, **kwargs)

        # For logging the timing in self.finalize_response
        self.requested_at = now()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super(LoggingMixin, self).finalize_response(
            request, response, *args, **kwargs
        )

        if not response.exception:
            # Don't log things like 401, 403, etc.,
            # noinspection PyBroadException
            try:
                results = self._log_request(request)
                self._handle_events(results, request.user)
            except Exception as e:
                logger.exception(
                    "Unable to log API response timing info: %s", e
                )
        return response

    def _get_response_ms(self):
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
        endpoint = resolve(request.path_info).url_name
        response_ms = self._get_response_ms()

        r = make_redis_interface("STATS")
        pipe = r.pipeline()

        # Global and daily tallies for all URLs.
        pipe.incr("api:v3.count")
        pipe.incr(f"api:v3.d:{d}.count")
        pipe.incr("api:v3.timing", response_ms)
        pipe.incr(f"api:v3.d:{d}.timing", response_ms)

        # Use a sorted set to store the user stats, with the score representing
        # the number of queries the user made total or on a given day.
        user_pk = user.pk or "AnonymousUser"
        pipe.zincrby("api:v3.user.counts", 1, user_pk)
        pipe.zincrby(f"api:v3.user.d:{d}.counts", 1, user_pk)

        # Use a sorted set to store all the endpoints with score representing
        # the number of queries the endpoint received total or on a given day.
        pipe.zincrby("api:v3.endpoint.counts", 1, endpoint)
        pipe.zincrby(f"api:v3.endpoint.d:{d}.counts", 1, endpoint)

        # We create a per-day key in redis for timings. Inside the key we have
        # members for every endpoint, with score of the total time. So to get
        # the average for an endpoint you need to get the number of requests
        # and the total time for the endpoint and divide.
        timing_key = f"api:v3.endpoint.d:{d}.timings"
        pipe.zincrby(timing_key, response_ms, endpoint)

        results = pipe.execute()
        return results

    def _handle_events(self, results, user):
        total_count = results[0]
        user_count = results[4]

        if total_count in MILESTONES_FLAT:
            Event.objects.create(
                description=f"API has logged {total_count} total requests."
            )
        if user.is_authenticated:
            if user_count in self.milestones:
                Event.objects.create(
                    description="User '%s' has placed their %s API request."
                    % (user.username, intcomma(ordinal(user_count))),
                    user=user,
                )


class CacheListMixin(object):
    """Cache listed results"""

    @method_decorator(cache_page(60))
    # Ensure that permissions are maintained and not cached!
    @method_decorator(vary_on_headers("Cookie", "Authorization"))
    def list(self, *args, **kwargs):
        return super(CacheListMixin, self).list(*args, **kwargs)


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


class EmailProcessingQueueAPIUsers(BasePermission):
    def has_permission(self, request, view):
        # TODO - This will check against an API token in the header. This will be stored in environment variables on either side. https://github.com/freelawproject/courtlistener/issues/1676
        return True


class TinyAdjustablePagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


class MediumAdjustablePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"


class BigPagination(PageNumberPagination):
    page_size = 300


class BulkJsonHistory(object):
    """Helpers for keeping track of data modified info on disk.

    Format of JSON data is:

    {
      "last_good_date": ISO-Date,
      "last_attempt: ISO-Date,
      "duration": seconds,
    }

    """

    def __init__(self, obj_type_str, bulk_dir):
        self.obj_type_str = obj_type_str
        self.path = os.path.join(bulk_dir, obj_type_str, "info.json")
        self.json = self.load_json_file()
        super(BulkJsonHistory, self).__init__()

    def load_json_file(self) -> Dict[str, Union[str, float]]:
        """Get the history file from disk and return it as data."""
        try:
            with open(self.path, "r") as f:
                try:
                    return json.load(f)
                except ValueError:
                    # When the file doesn't exist.
                    return {}
        except IOError as e:
            # Happens when the directory isn't even there.
            return {}

    def save_to_disk(self):
        filepath = self.path.rsplit("/", 1)[0]
        Path(filepath).mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as f:
            json.dump(self.json, f, indent=2)

    def delete_from_disk(self):
        try:
            os.remove(self.path)
        except OSError as e:
            if e.errno != 2:
                # Problem other than No such file or directory.
                raise

    def get_last_good_date(self):
        """Get the last good date from the file, or return None."""
        d = self.json.get("last_good_date", None)
        if d is None:
            return d
        else:
            return parser.parse(d)

    def get_last_attempt(self):
        """Get the last attempt from the file, or return None."""
        d = self.json.get("last_attempt", None)
        if d is None:
            return d
        else:
            return parser.parse(d)

    def add_current_attempt_and_save(self):
        """Add an attempt as the current attempt."""
        self.json["last_attempt"] = now().isoformat()
        self.save_to_disk()

    def mark_success_and_save(self):
        """Note a successful run."""
        n = now()
        self.json["last_good_date"] = n.isoformat()
        try:
            duration = n - parser.parse(self.json["last_attempt"])
            self.json["duration"] = int(duration.total_seconds())
        except KeyError:
            # last_attempt wasn't set ahead of time.
            self.json["duration"] = "Unknown"
        self.save_to_disk()


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
    """Invert the user logs for a period of time

    The user logs have the date in the key and the user as part of the set:

        'api:v3.user.d:2016-10-01.counts': {
           mlissner: 22,
           joe_hazard: 33,
        }

    This inverts these entries to:

        users: {
            mlissner: {
                2016-10-01: 22,
                total: 22,
            },
            joe_hazard: {
                2016-10-01: 33,
                total: 33,
            }
        }
    :param start: The beginning date (inclusive) you want the results for. A
    :param end: The end date (inclusive) you want the results for.
    :param add_usernames: Stats are stored with the user ID. If this is True,
    add an alias in the returned dictionary that contains the username as well.
    :return The inverted dictionary
    """
    r = make_redis_interface("STATS")
    pipe = r.pipeline()

    dates = make_date_str_list(start, end)
    for d in dates:
        pipe.zrange(f"api:v3.user.d:{d}.counts", 0, -1, withscores=True)
    results = pipe.execute()

    # results is a list of results for each of the zrange queries above. Zip
    # those results with the date that created it, and invert the whole thing.
    out: defaultdict = defaultdict(dict)
    for d, result in zip(dates, results):
        for user_id, count in result:
            if user_id == "None" or user_id == "AnonymousUser":
                user_id = "AnonymousUser"
            else:
                user_id = int(user_id)
            count = int(count)
            if out.get(user_id):
                out[user_id][d] = count
                out[user_id]["total"] += count
            else:
                out[user_id] = {d: count, "total": count}

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

    :param start: The beginning of when you want to find users (default: all
    time). A str to be interpreted by dateparser.
    :param end: The end of when you want to find users (default today).  A
    str to be interpreted by dateparser.
    :return Set of user IDs during a time period. Will not contain anonymous
    users.
    """
    r = make_redis_interface("STATS")
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
    r = make_redis_interface("STATS")
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
    r = make_redis_interface("STATS")
    pipe = r.pipeline()
    pipe.zscore(f"api:v3.endpoint.d:{d_str}.timings", endpoint)
    pipe.zscore(f"api:v3.endpoint.d:{d_str}.counts", endpoint)
    results = pipe.execute()

    return results[0] / results[1]


def get_replication_statuses() -> Dict[str, List[Dict[str, Union[str, int]]]]:
    """Return the replication status information for all publishers

    The easiest way to detect a problem in a replication set up is to monitor
    the size of the publisher's change lag. That is, how many changes are on
    the publisher that haven't been sent to the subscriber? This function will
    query all DBs set up in the config file and send their replication status
    information.

    :return: The status of all configured publications
    :rtype: A dict of server aliases point to lists of query results dicts:

    {"replica": [{
            slot_name: 'coupa',
            lsn_distance: 33239
        }, {
            slot_name: 'maverick',
            lsn_distance: 393478,
        }],
        "default": [{
            slot_name: 'replica',
            lsn_distance: 490348
        }],
    }
    """
    statuses = {}
    query = """
        SELECT
            slot_name,
            confirmed_flush_lsn,
            pg_current_wal_lsn(),
            (pg_current_wal_lsn() - confirmed_flush_lsn) AS lsn_distance
        FROM pg_replication_slots;
    """
    for alias in connections:
        with connections[alias].cursor() as cursor:
            cursor.execute(query)
            rows = fetchall_as_dict(cursor)
            if rows:
                statuses[alias] = rows
    return statuses
