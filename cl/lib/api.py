import re
from lxml import etree
from tastypie import http
from tastypie.resources import ModelResource
from tastypie.throttle import CacheThrottle

from cl import settings
from cl.lib import search_utils
from cl.lib.string_utils import filter_invalid_XML_chars
from cl.lib.sunburnt import SolrError, sunburnt
from cl.search import forms

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
        data['meta']['donate'] = 'Please donate today to support more ' \
                                 'projects from Free Law Project.'
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
        for k, v in bundle.data.items():
            bundle.data[k] = filter_invalid_XML_chars(v)
        return bundle



class PerUserCacheThrottle(CacheThrottle):
    """Sets up higher throttles for specific users"""
    custom_throttles = {
        'scout': 10000,
        'scout_test': 10000,
        'mlissner': 1e9,  # A billion because I made this.
    }


def get_object_list(request=None, **kwargs):
    """Perform the Solr work"""
    # Set the offset value
    paginator = kwargs['paginator']
    page_number = int(request.GET.get(paginator.page_query_param, 1))
    # Assume page_size = 20, then: 1 --> 0, 2 --> 19, 3 --> 39
    offset = max(0, (page_number - 1) * paginator.page_size - 1)
    limit = 20
    main_query = {'caller': 'api_search'}
    try:
        main_query.update(search_utils.build_main_query(
            kwargs['cd'],
            highlight='text'
        ))
        sl = SolrList(
            main_query=main_query,
            offset=offset,
            limit=limit,
            type=kwargs['cd']['type'],
        )
    except KeyError:
        sf = forms.SearchForm({'q': '*:*'})
        if sf.is_valid():
            main_query.update(search_utils.build_main_query(
                sf.cleaned_data,
                highlight='text',
            ))
        sl = SolrList(
            main_query=main_query,
            offset=offset,
            limit=limit,
        )
    return sl


class SolrList(object):
    """This implements a yielding list object that fetches items as they are
    queried.
    """

    def __init__(self, main_query, offset, limit, type=None, length=None):
        super(SolrList, self).__init__()
        self.main_query = main_query
        self.offset = offset
        self.limit = limit
        self.type = type
        self._item_cache = []
        if self.type == 'o':
            self.conn = sunburnt.SolrInterface(
                settings.SOLR_OPINION_URL, mode='r')
        elif self.type == 'oa':
            self.conn = sunburnt.SolrInterface(
                settings.SOLR_AUDIO_URL, mode='r')
        self._length = length

    def __len__(self):
        if self._length is None:
            mq = self.main_query.copy()  # local copy for manipulation
            mq['rows'] = 0  # For performance, we just want the count
            mq['caller'] = 'api_search_count'
            r = self.conn.raw_query(**mq).execute()
            self._length = r.result.numFound
        return self._length

    def __iter__(self):
        for item in range(0, len(self)):
            try:
                yield self._item_cache[item]
            except IndexError:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        self.main_query['start'] = self.offset
        results_si = self.conn.raw_query(**self.main_query).execute()

        # Pull the text snippet up a level, where tastypie can find it
        for result in results_si.result.docs:
            result['snippet'] = '&hellip;'.join(
                result['solr_highlights']['text'])

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
        """Lightly override the append method so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class SolrObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data
