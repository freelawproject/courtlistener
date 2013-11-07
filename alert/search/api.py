import logging
from tastypie import fields
from tastypie.authentication import BasicAuthentication, SessionAuthentication, MultiAuthentication
from tastypie.constants import ALL
from tastypie.exceptions import BadRequest
from tastypie.paginator import Paginator
from tastypie.resources import ModelResource, Resource
from tastypie.throttle import CacheThrottle
from alert import settings
from alert.lib import search_utils
from alert.lib.search_utils import build_main_query
from alert.lib.string_utils import filter_invalid_XML_chars
from alert.lib.sunburnt import sunburnt
from alert.search.forms import SearchForm
from alert.search.models import Citation, Court, Document
from alert.stats import tally_stat

logger = logging.getLogger(__name__)

good_time_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',
                     'year', 'month', 'day', 'hour', 'minute', 'second',)
good_date_filters = good_time_filters[:-3]
numerical_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',)


class ModelResourceWithFieldsFilter(ModelResource):
    def full_dehydrate(self, bundle, *args, **kwargs):
        bundle = super(ModelResourceWithFieldsFilter, self).full_dehydrate(bundle, *args, **kwargs)
        # bundle.obj[0]._data['citeCount'] = 0
        fields = bundle.request.GET.get("fields", "")
        if fields:
            fields = fields.split(",")
            new_data = {}
            for k in fields:
                if k in bundle.data:
                    new_data[k] = bundle.data[k]
            bundle.data = new_data
        return bundle

    def dehydrate(self, bundle):
        # Strip invalid XML chars before serializing
        for k, v in bundle.data.iteritems():
            bundle.data[k] = filter_invalid_XML_chars(v)
        return bundle


class CourtResource(ModelResourceWithFieldsFilter):
    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        resource_name = 'jurisdiction'
        queryset = Court.objects.exclude(jurisdiction='T')
        max_limit = 20
        allowed_methods = ['get']
        filtering = {
            'id': ('exact',),
            'date_modified': good_time_filters,
            'in_use': ALL,
            'position': numerical_filters,
            'short_name': ALL,
            'full_name': ALL,
            'URL': ALL,
            'start_date': good_date_filters,
            'end_date': good_date_filters,
            'jurisdictions': ALL,
        }
        ordering = ['date_modified', 'start_date', 'end_date', 'position', 'jurisdiction']


class CitationResource(ModelResourceWithFieldsFilter):
    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        queryset = Citation.objects.all()
        max_limit = 20
        excludes = ['slug', ]


class DocumentResource(ModelResourceWithFieldsFilter):
    citation = fields.ForeignKey(CitationResource, 'citation')
    court = fields.ForeignKey(CourtResource, 'court')
    cases_cited = fields.ManyToManyField(CitationResource, 'cases_cited', use_in='detail')
    html = fields.CharField(attribute='html', use_in='detail', null=True)
    html_lawbox = fields.CharField(attribute='html_lawbox', use_in='detail', null=True)
    html_with_citations = fields.CharField(attribute='html_with_citations', use_in='detail', null=True)
    plain_text = fields.CharField(attribute='plain_text', use_in='detail', null=True)

    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        resource_name = 'opinion'
        queryset = Document.objects.all().select_related('court__pk', 'citation__pk', 'citation__slug')
        max_limit = 20
        allowed_methods = ['get']
        include_absolute_url = True
        excludes = ['is_stub_document']
        filtering = {
            'id': ('exact',),
            'time_retrieved': good_time_filters,
            'date_modified': good_time_filters,
            'date_filed': good_date_filters,
            'sha1': ('exact',),
            'court': ('exact',),
            'citation': numerical_filters,
            'citation_count': numerical_filters,
            'precedential_status': ('exact', 'in'),
            'date_blocked': good_date_filters,
            'blocked': ALL,
            'extracted_by_ocr': ALL,
        }
        ordering = ['time_retrieved', 'date_modified', 'date_filed', 'pagerank', 'date_blocked']


class SolrList(list):
    def __init__(self, conn, q, length, offset, limit):
        super(SolrList, self).__init__()
        self.q = q
        self.conn = conn
        self.length = length
        self._item_cache = []
        self.offset = offset
        self.limit = limit

    def __len__(self):
        """Tastypie's paginator takes the len() of the item for its work."""
        return self.length

    def __iter__(self):
        for item in range(0, self.length):
            if self._item_cache[item]:
                yield self._item_cache[item]
            else:
                yield self.__getitem__(item)

    def _get_offset(self, item):
        return item + 1

    def __getitem__(self, item):
        if item > (self.offset - 1 + self.limit):
            # If the item is outside of our initial query, we need to get items and put them in our cache
            self._item_cache = []
            self.q['offset'] = self._get_offset(item)
            results_si = self.conn.raw_query(**self.q).execute()
            for result in results_si.result.docs:
                self._item_cache.append(SolrObject(initial=result))

        # Now, assuming our _item_cache is all set, we just get the item.
        return self._item_cache[item]

    def append(self, p_object):
        """Lightly override the append method so we get items duplicated in our cache."""
        super(SolrList, self).append(p_object)
        self._item_cache.append(p_object)


class SolrObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data


class SearchResource(ModelResourceWithFieldsFilter):
    # Roses to the person that makes this introspect and removes all this code.
    id = fields.CharField(attribute='id', default='id')
    status = fields.CharField(attribute='status', default='status')
    suitNature = fields.CharField(attribute='suitNature', default='suitNature')
    court = fields.CharField(attribute='court', default='court')
    caseName = fields.CharField(attribute='caseName', default='caseName')
    citeCount = fields.IntegerField(attribute='citeCount', default='citeCount')
    text = fields.CharField(attribute='text', default='text', use_in='detail')  # Only shows on the detail page.
    citation = fields.CharField(attribute='citation', default='citation')
    download_url = fields.CharField(attribute='download_url', default='download_url')
    dateFiled = fields.DateField(attribute='dateFiled', default='dateFiled')
    source = fields.CharField(attribute='source', default='source')
    local_path = fields.CharField(attribute='local_path', default='local_path')
    court_id = fields.CharField(attribute='court_id', default='court_id')
    absolute_url = fields.CharField(attribute='absolute_url', default='absolute_url')
    judge = fields.CharField(attribute='judge', default='judge')
    docketNumber = fields.CharField(attribute='docketNumber', default='docketNumber')
    caseNumber = fields.CharField(attribute='caseNumber', default='caseNumber')
    timestamp = fields.DateField(attribute='timestamp', default='timestamp')
    score = fields.FloatField(attribute='score', default='score')

    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        resource_name = 'search'
        max_limit = 20
        allowed_methods = ['get']

    def get_resource_uri(self, bundle_or_obj=None, url_name='api_dispatch_list'):
        """Creates a URI like /api/v1/search/$id/
        """
        url_str = '/api/%s/%s/%s/'
        if bundle_or_obj:
            return url_str % (
                self.api_name,
                self._meta.resource_name,
                bundle_or_obj.obj.id,
            )
        else:
            return ''

    def get_object_list(self, request=None, **kwargs):
        """Performs the Solr work."""
        conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
        try:
            main_query = build_main_query(kwargs['cd'], highlight=False)
        except KeyError:
            main_query = {'q': "*:*"}

        results_si = conn.raw_query(**main_query).execute()
        # Return the results as objects, not dicts.
        # Use a SolrList that has a couple of the normal functions built in.
        sl = SolrList(conn=conn, q=main_query, length=results_si.result.numFound,
                      offset=request.GET.get('offset', 0), limit=request.GET.get('limit', 20))
        for result in results_si.result.docs:
            sl.append(SolrObject(initial=result))
        return sl

    def obj_get_list(self, bundle, **kwargs):
        search_form = SearchForm(bundle.request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if cd['q'] == '':
                cd['q'] = '*:*'  # Get everything.
            return self.get_object_list(bundle.request, cd=cd)
        else:
            BadRequest("Invalid resource lookup data provided. Unable to complete your query.")

    def obj_get(self, bundle, **kwargs):
        search_form = SearchForm(bundle.request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            cd['q'] = 'id:%s' % kwargs['pk']
            return self.get_object_list(bundle.request, cd=cd)[0]
        else:
            BadRequest("Invalid resource lookup data provided. Unable to complete your request.")