import json
import os
from collections import OrderedDict, defaultdict
from datetime import date

import redis
from dateutil import parser
from dateutil.rrule import DAILY, rrule
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import intcomma, ordinal
from django.core.mail import send_mail
from django.utils.decorators import method_decorator
from django.utils.encoding import force_text
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework import serializers
from rest_framework.metadata import SimpleMetadata
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.request import clone_request
from rest_framework.throttling import UserRateThrottle
from rest_framework_filters import RelatedFilter
from rest_framework_filters.backends import DjangoFilterBackend

from cl.lib.utils import mkdir_p
from cl.stats.models import Event
from cl.stats.utils import MILESTONES_FLAT, get_milestone_range

DATETIME_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range', 'year',
                    'month', 'day', 'hour', 'minute', 'second']
DATE_LOOKUPS = DATETIME_LOOKUPS[:-3]
INTEGER_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range']
BASIC_TEXT_LOOKUPS = ['exact', 'iexact', 'startswith', 'istartswith',
                      'endswith', 'iendswith']
ALL_TEXT_LOOKUPS = BASIC_TEXT_LOOKUPS + ['contains', 'icontains']


class HyperlinkedModelSerializerWithId(serializers.HyperlinkedModelSerializer):
    """Extend the HyperlinkedModelSerializer to add IDs as well for the best of
    both worlds.
    """
    id = serializers.ReadOnlyField()


class DisabledHTMLFilterBackend(DjangoFilterBackend):
    """Disable showing filters in the browsable API.

    Ideally, we'd want to show fields in the browsable API, but for related
    objects this loads every object into the HTML and it loads them from the DB
    one query at a time. It's insanity, so it's gotta be disabled globally.
    """
    def to_html(self, request, queryset, view):
        return ""


class SimpleMetadataWithFilters(SimpleMetadata):

    def determine_metadata(self, request, view):
        metadata = super(SimpleMetadataWithFilters, self).determine_metadata(request, view)
        filters = OrderedDict()
        if not hasattr(view, 'filter_class'):
            # This is the API Root, which is not filtered.
            return metadata

        for filter_name, filter_type in view.filter_class.base_filters.items():
            filter_parts = filter_name.split('__')
            filter_name = filter_parts[0]
            attrs = OrderedDict()

            # Type
            attrs['type'] = filter_type.__class__.__name__

            # Lookup fields
            if len(filter_parts) > 1:
                # Has a lookup type (__gt, __lt, etc.)
                lookup_type = filter_parts[1]
                if filters.get(filter_name) is not None:
                    # We've done a filter with this name previously, just
                    # append the value.
                    attrs['lookup_types'] = filters[filter_name]['lookup_types']
                    attrs['lookup_types'].append(lookup_type)
                else:
                    attrs['lookup_types'] = [lookup_type]
            else:
                # Exact match or RelatedFilter
                if isinstance(filter_type, RelatedFilter):
                    model_name = (filter_type.filterset.Meta.model.
                                  _meta.verbose_name_plural.title())
                    attrs['lookup_types'] = "See available filters for '%s'" % \
                                            model_name
                else:
                    attrs['lookup_types'] = ['exact']

            # Do choices
            choices = filter_type.extra.get('choices', False)
            if choices:
                attrs['choices'] = [
                    {
                        'value': choice_value,
                        'display_name': force_text(choice_name, strings_only=True)
                    }
                    for choice_value, choice_name in choices
                ]

            # Wrap up.
            filters[filter_name] = attrs

        metadata['filters'] = filters

        if hasattr(view, 'ordering_fields'):
            metadata['ordering'] = view.ordering_fields
        return metadata

    def determine_actions(self, request, view):
        """Simple override to always show the field information even for people
        that don't have POST access.

        Fixes issue #732.
        """
        actions = {}
        for method in {'PUT', 'POST'} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            if method == 'PUT' and hasattr(view, 'get_object'):
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
    milestones = get_milestone_range('SM', 'XXXL')

    def initial(self, request, *args, **kwargs):
        super(LoggingMixin, self).initial(request, *args, **kwargs)

        d = date.today().isoformat()
        user = request.user
        endpoint = request.resolver_match.url_name

        r = redis.StrictRedis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DATABASES['STATS'],
        )
        pipe = r.pipeline()

        # Global and daily tallies for all URLs.
        pipe.incr('api:v3.count')
        pipe.incr('api:v3.d:%s.count' % d)

        # Use a sorted set to store the user stats, with the score representing
        # the number of queries the user made total or on a given day.
        pipe.zincrby('api:v3.user.counts', user.pk)
        pipe.zincrby('api:v3.user.d:%s.counts' % d, user.pk)

        # Use a sorted set to store all the endpoints with score representing
        # the number of queries the endpoint received total or on a given day.
        pipe.zincrby('api:v3.endpoint.counts', endpoint)
        pipe.zincrby('api:v3.endpoint.d:%s.counts' % d, endpoint)

        results = pipe.execute()
        total_count = results[0]
        user_count = results[2]

        if total_count in MILESTONES_FLAT:
            Event.objects.create(description="API has logged %s total requests."
                                             % total_count)
        if user.is_authenticated():
            if user_count in self.milestones:
                Event.objects.create(
                    description="User '%s' has placed their %s API request." %
                                (user.username, intcomma(ordinal(user_count))),
                    user=user,
                )
            if user_count == 5:
                email = emails['new_api_user']
                send_mail(
                    email['subject'],
                    email['body'] % user.first_name or 'there',
                    email['from'],
                    [user.email],
                )


class CacheListMixin(object):
    """Cache listed results"""

    @method_decorator(cache_page(60))
    # Ensure that permissions are maintained and not cached!
    @method_decorator(vary_on_headers('Cookie', 'Authorization'))
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
        override_rate = settings.REST_FRAMEWORK['OVERRIDE_THROTTLE_RATES'].get(
            request.user.username,
            None,
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
        'GET': ['%(app_label)s.has_recap_api_access'],
        'OPTIONS': ['%(app_label)s.has_recap_api_access'],
        'HEAD': ['%(app_label)s.has_recap_api_access'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


class RECAPUploaders(DjangoModelPermissions):
    """Provides some users upload permissions in RECAP

    Such users must have the has_recap_upload_access flag set on their account
    """
    perms_map = {
        'GET': ['%(app_label)s.has_recap_upload_access'],
        'OPTIONS': ['%(app_label)s.has_recap_upload_access'],
        'HEAD': ['%(app_label)s.has_recap_upload_access'],
        'POST': ['%(app_label)s.has_recap_upload_access'],
        'PUT': ['%(app_label)s.has_recap_upload_access'],
        'PATCH': ['%(app_label)s.has_recap_upload_access'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


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
        self.path = os.path.join(bulk_dir, 'tmp', obj_type_str,
                                 'info.json')
        self.json = self.load_json_file()
        super(BulkJsonHistory, self).__init__()

    def load_json_file(self):
        """Get the history file from disk and return it as data."""
        try:
            with open(self.path, 'r') as f:
                try:
                    return json.load(f)
                except ValueError:
                    # When the file doesn't exist.
                    return {}
        except IOError as e:
            # Happens when the directory isn't even there.
            return {}

    def save_to_disk(self):
        mkdir_p(self.path.rsplit('/', 1)[0])
        with open(self.path, 'w') as f:
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
        d = self.json.get('last_good_date', None)
        if d is None:
            return d
        else:
            return parser.parse(d)

    def get_last_attempt(self):
        """Get the last attempt from the file, or return None."""
        d = self.json.get('last_attempt', None)
        if d is None:
            return d
        else:
            return parser.parse(d)

    def add_current_attempt_and_save(self):
        """Add an attempt as the current attempt."""
        self.json['last_attempt'] = now().isoformat()
        self.save_to_disk()

    def mark_success_and_save(self):
        """Note a successful run."""
        n = now()
        self.json['last_good_date'] = n.isoformat()
        try:
            duration = n - parser.parse(self.json['last_attempt'])
            self.json['duration'] = int(duration.total_seconds())
        except KeyError:
            # last_attempt wasn't set ahead of time.
            self.json['duration'] = "Unknown"
        self.save_to_disk()


def invert_user_logs(start, end):
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
    """
    r = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES['STATS'],
    )
    pipe = r.pipeline()

    dates = [d.date().isoformat() for d in rrule(
        DAILY,
        dtstart=parser.parse(start, fuzzy=False),
        until=parser.parse(end, fuzzy=False),
    )]
    for d in dates:
        pipe.zrange('api:v3.user.d:%s.counts' % d, 0, -1,
                    withscores=True)
    results = pipe.execute()

    # results is a list of results for each of the zrange queries above. Zip
    # those results with the date that created it, and invert the whole thing.
    out = defaultdict(dict)
    for d, result in zip(dates, results):
        for user_id, count in result:
            if user_id == 'None':
                continue
            user_id = int(user_id)
            count = int(count)
            if out.get(user_id):
                out[user_id][d] = count
                out[user_id]['total'] += count
            else:
                out[user_id] = {d: count, 'total': count}

    # Sort the values
    for k, v in out.items():
        out[k] = OrderedDict(sorted(v.items(), key=lambda t: t[0]))

    # Add usernames as alternate keys for every value possible.
    for k, v in out.items():
        try:
            user = User.objects.get(pk=k)
        except (User.DoesNotExist, ValueError):
            pass
        else:
            out[user.username] = v

    return out


emails = {
    'new_api_user': {
        'subject': "Welcome to the CourtListener API from Free Law Project",
        'body': ("Hi %s,\n\n"
                 "I'm Mike Lissner, the main guy behind CourtListener and Free "
                 "Law Project, the non-profit that runs it. I noticed that you "
                 "started using the API a bit today (we watch our logs closely "
                 "when it comes to the API!) and I just wanted to reach out, "
                 "say hello, and make sure that everything is working properly "
                 "and making sense.\n\n"
                 "We've found that the API can be a bit complicated at first, "
                 "and that sometimes it helps to get a quick conversation "
                 "going when people are first exploring the APIs.\n\n"
                 "Feel free to respond to this email with any questions that "
                 "come up or comments that occur to you about the API, and I "
                 "can usually respond pretty quickly to help out or address "
                 "issues.\n\n"
                 "Enjoy the API and thanks for giving it a try!\n\n"
                 "Mike Lissner\n"
                 "Founder, Free Law Project\n"
                 "https://www.courtlistener.com/donate/\n"),
        'from': "Mike Lissner <mlissner@courtlistener.com>",
    },
}
