import re
import time
from django.core.cache import cache
from lxml import etree
from tastypie import http
from tastypie.authentication import BasicAuthentication
from tastypie.resources import ModelResource
from tastypie.throttle import CacheThrottle
from alert import settings
from alert.lib.string_utils import filter_invalid_XML_chars
from alert.lib.sunburnt import SolrError, sunburnt
from alert.stats import tally_stat

good_time_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',
                     'year', 'month', 'day', 'hour', 'minute', 'second',)
good_date_filters = good_time_filters[:-3]
numerical_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',)


class ModelResourceWithFieldsFilter(ModelResource):
    def __init__(self, tally_name=None):
        super(ModelResourceWithFieldsFilter, self).__init__()
        self.tally_name = tally_name

    def _handle_500(self, request, exception):
        # Note that this will only be run if DEBUG=False
        if isinstance(exception, SolrError):
            solr_status_code = exception[0]['status']
            error_xml = etree.fromstring(exception[1])
            solr_msg = error_xml.xpath('//lst[@name = "error"]/str[@name = "msg"]/text()')[0]
            data = {
                'error_message': "SolrError raised while interpreting your query.",
                'solr_status_code': solr_status_code,
                'solr_msg': solr_msg,
            }
            return self.error_response(
                request,
                data,
                response_class=http.HttpApplicationError
            )
        else:
            return super(ModelResourceWithFieldsFilter, self)._handle_500(request, exception)

    def alter_list_data_to_serialize(self, request, data):
        # Add a request_uri field
        data['meta']['request_uri'] = request.get_full_path()

        return data

    def full_dehydrate(self, bundle, *args, **kwargs):
        bundle = super(ModelResourceWithFieldsFilter, self).full_dehydrate(bundle, *args, **kwargs)
        # bundle.obj[0]._data['citeCount'] = 0
        fields = bundle.request.GET.get("fields", "")
        if fields:
            fields_list = re.split(',|__', fields)
            new_data = {}
            for k in fields_list:
                if k in bundle.data:
                    new_data[k] = bundle.data[k]
            bundle.data = new_data
        return bundle

    def dehydrate(self, bundle):
        # Strip invalid XML chars before serializing
        for k, v in bundle.data.iteritems():
            bundle.data[k] = filter_invalid_XML_chars(v)
        return bundle

    def dispatch(self, request_type, request, **kwargs):
        """Simple override here to tally stats before sending off the results."""
        tally_stat(self.tally_name)
        return super(ModelResourceWithFieldsFilter, self).dispatch(request_type, request, **kwargs)


class DeprecatedModelResourceWithFieldsFilter(ModelResourceWithFieldsFilter):
    def __init__(self, tally_name=None):
        super(DeprecatedModelResourceWithFieldsFilter, self).__init__(tally_name=tally_name)

    def alter_list_data_to_serialize(self, request, data):
        # Add a request_uri field
        data['meta']['status'] = 'This endpoint is deprecated. Please upgrade to a newer version of the API.'

        return super(DeprecatedModelResourceWithFieldsFilter, self).alter_list_data_to_serialize(request, data)


class BasicAuthenticationWithUser(BasicAuthentication):
    """Wraps the BasicAuthentication class, changing the get_identifier method to provide the username instead of
    essentially nothing.

    Proposed this change in: https://github.com/toastdriven/django-tastypie/pull/1085/commits
    """
    def __init__(self, backend=None, realm='django-tastypie', **kwargs):
        super(BasicAuthenticationWithUser, self).__init__(backend, realm, **kwargs)

    def get_identifier(self, request):
        return request.META.get('REMOTE_USER', request.user.username)


class PerUserCacheThrottle(CacheThrottle):
    """Sets up higher throttles for specific users"""
    custom_throttles = {
        'scout': 10000,
        'scout_test': 10000,
        'mlissner': 1e9,  # A billion because I made this.
    }

    def should_be_throttled(self, identifier, **kwargs):
        """
        Lightly edits the inherited method to add an additional check of the
        `custom_throttles` variable.

        Returns whether or not the user has exceeded their throttle limit.

        Maintains a list of timestamps when the user accessed the api within
        the cache.

        Returns ``False`` if the user should NOT be throttled or ``True`` if
        the user should be throttled.
        """
        key = self.convert_identifier_to_key(identifier)

        # Make sure something is there.
        cache.add(key, [])

        # Weed out anything older than the timeframe.
        minimum_time = int(time.time()) - int(self.timeframe)
        times_accessed = [access for access in cache.get(key) if access >= minimum_time]
        cache.set(key, times_accessed, self.expiration)

        throttle_at = self.custom_throttles.get(identifier, int(self.throttle_at))
        if len(times_accessed) >= throttle_at:
            # Throttle them.
            return True

        # Let them through.
        return False


class SolrList(object):
    """This implements a yielding list object that fetches items as they are queried."""
    def __init__(self, main_query, offset, limit, length=None):
        super(SolrList, self).__init__()
        self.main_query = main_query
        self.offset = offset
        self.limit = limit
        self.length = length
        self._item_cache = []
        self.conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')

    def __len__(self):
        """Tastypie's paginator takes the len() of the item for its work."""
        if self.length is None:
            mq = self.main_query.copy()  # local copy for manipulation
            mq['rows'] = 0  # For performance, we just want the count
            mq['caller'] = 'api_search_count'
            r = self.conn.raw_query(**mq).execute()
            self.length = r.result.numFound
        return self.length

    def __iter__(self):
        for item in range(0, self.length):
            if self._item_cache[item]:
                yield self._item_cache[item]
            else:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        self.main_query['start'] = self.offset
        results_si = self.conn.raw_query(**self.main_query).execute()

        # Set the length if it's not yet set.
        if self.length is None:
            self.length = results_si.result.numFound

        # Pull the text snippet up a level, where tastypie can find it
        for result in results_si.result.docs:
            result['snippet'] = '&hellip;'.join(result['solr_highlights']['text'])

        # Return the results as objects, not dicts.
        for result in results_si.result.docs:
            self._item_cache.append(SolrObject(initial=result))

        # Now, assuming our _item_cache is all set, we just get the item.
        if isinstance(item, slice):
            s = slice(item.start - int(self.offset),
                      item.stop - int(self.offset),
                      item.step)
            return self._item_cache[s]
        else:
            # Not slicing.
            try:
                return self._item_cache[item]
            except IndexError:
                # No results!
                return []

    def append(self, p_object):
        """Lightly override the append method so we get items duplicated in our cache."""
        self._item_cache.append(p_object)


class SolrObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data
