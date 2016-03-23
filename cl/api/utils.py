import json
import os
from collections import OrderedDict
from datetime import date

import redis
from dateutil import parser
from django.conf import settings
from django.utils.encoding import force_text
from django.utils.timezone import now
from rest_framework import serializers
from rest_framework.metadata import SimpleMetadata
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.throttling import UserRateThrottle
from rest_framework_filters import RelatedFilter

from cl.lib.utils import mkdir_p

DATETIME_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range', 'year',
                    'month', 'day', 'hour', 'minute', 'second']
DATE_LOOKUPS = DATETIME_LOOKUPS[:-3]
INTEGER_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range']
BASIC_TEXT_LOOKUPS = ['exact', 'iexact', 'startswith', 'istartswith',
                      'endswith', 'iendswith']
ALL_TEXT_LOOKUPS = BASIC_TEXT_LOOKUPS + ['contains', 'icontains']


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)
        if not self.context or not self.context.get('request'):
            # This happens during initialization.
            return
        fields = getattr(self.context['request'], 'query_params', {}).get('fields')
        if fields is not None:
            fields = fields.split(',')
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)


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

        metadata['ordering'] = view.ordering_fields
        return metadata


class LoggingMixin(object):
    """Log requests to Redis

    This draws inspiration from the code that can be found at: https://github.com/aschn/drf-tracking/blob/master/rest_framework_tracking/mixins.py

    The big distinctions, however, are that this code uses Redis for greater
    speed, and that it logs significantly less information.

    We want to know:
     - How many queries in last X days, total?
     - How many queries ever, total?
     - How many queries total made by user X?
     - How many queries per day made by user X?
    """

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

        pipe.execute()


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


class BetaUsersReadOnly(DjangoModelPermissions):
    """Provides access beta access to users with the right permissions.

    Such users must have the has_beta_api_access flag set on their account.
    """

    perms_map = {
        'GET': ['%(app_label)s.has_beta_api_access'],
        'OPTIONS': ['%(app_label)s.has_beta_api_access'],
        'HEAD': ['%(app_label)s.has_beta_api_access'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


class BulkJsonHistory(object):
    """Helpers for keeping track of data modified info on disk.

    Format of JSON data is:

    {
      "last_good_date": ISO-Date,
      "last_attempt: ISO-Date,
      "duration": seconds,
    }

    """

    def __init__(self, obj_type_str):
        self.obj_type_str = obj_type_str
        self.path = os.path.join(settings.BULK_DATA_DIR, 'tmp', obj_type_str,
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
