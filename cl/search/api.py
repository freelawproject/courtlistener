import logging

from cl.lib.api import DeprecatedModelResourceWithFieldsFilter, \
    BasicAuthenticationWithUser, PerUserCacheThrottle, SolrList, \
    good_time_filters, numerical_filters, good_date_filters
from cl.lib.search_utils import build_main_query
from cl.search import forms
from cl.search.models import Court, SOURCES, \
    DOCUMENT_STATUSES

from tastypie import fields
from tastypie import authentication
from tastypie.constants import ALL
from tastypie.exceptions import BadRequest
from search.api2 import DocketResource

logger = logging.getLogger(__name__)


class JurisdictionResource(DeprecatedModelResourceWithFieldsFilter):
    has_scraper = fields.BooleanField(
        attribute='has_opinion_scraper',
        help_text='Whether the jurisdiction has a scraper that obtains '
                  'opinions automatically.'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        resource_name = 'jurisdiction'
        queryset = Court.objects.exclude(jurisdiction='T')
        max_limit = 1000
        allowed_methods = ['get']
        filtering = {
            'id': ('exact',),
            'date_modified': good_time_filters,
            'in_use': ALL,
            'has_scraper': ALL,
            'position': numerical_filters,
            'short_name': ALL,
            'full_name': ALL,
            'url': ALL,
            'start_date': good_date_filters,
            'end_date': good_date_filters,
            'jurisdictions': ALL,
        }
        ordering = ['date_modified', 'start_date', 'end_date', 'position',
                    'jurisdiction']
        excludes = ['has_opinion_scraper', 'has_oral_argument_scraper']


class CitationResource(DeprecatedModelResourceWithFieldsFilter):
    opinion_uris = fields.ToManyField(
        'search.api.DocumentResource',
        'parent_documents'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        queryset = Citation.objects.all()
        max_limit = 20
        excludes = ['slug', ]


class DocumentResource(DeprecatedModelResourceWithFieldsFilter):
    citation = fields.ForeignKey(
        CitationResource,
        'citation',
        full=True
    )
    court = fields.ForeignKey(
        JurisdictionResource,
        'docket__court'
    )
    html = fields.CharField(
        attribute='html',
        use_in='detail',
        null=True,
        help_text='HTML of the document, if available in the original'
    )
    html_lawbox = fields.CharField(
        attribute='html_lawbox',
        use_in='detail',
        null=True,
        help_text='HTML of lawbox documents'
    )
    html_with_citations = fields.CharField(
        attribute='html_with_citations',
        use_in='detail',
        null=True,
        help_text="HTML of the document with citation links and other "
                  "post-processed markup added",
    )
    plain_text = fields.CharField(
        attribute='plain_text',
        use_in='detail',
        null=True,
        help_text="Plain text of the document after extraction using "
                  "pdftotext, wpd2txt, etc.",
    )
    date_modified = fields.DateTimeField(
        attribute='date_modified',
        null=True,
        default='1750-01-01T00:00:00Z',
        help_text='The last moment when the item was modified. A value  in '
                  'year 1750 indicates the value is unknown'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        resource_name = 'opinion'
        queryset = Document.objects.all().select_related('docket__court__pk',
                                                         'citation')
        max_limit = 20
        allowed_methods = ['get']
        include_absolute_url = True
        excludes = ['opinions_cited', 'supreme_court_db_id',]
        filtering = {
            'id': ('exact',),
            'date_created': good_time_filters,
            'date_modified': good_time_filters,
            'date_filed': good_date_filters,
            'sha1': ('exact',),
            'court': ('exact',),
            'citation': ALL,
            'citation_count': numerical_filters,
            'precedential_status': ('exact', 'in'),
            'date_blocked': good_date_filters,
            'blocked': ALL,
            'extracted_by_ocr': ALL,
        }
        ordering = ['date_created', 'date_modified', 'date_filed',
                    'date_blocked']


class CitedByResource(DeprecatedModelResourceWithFieldsFilter):
    citation = fields.ForeignKey(
        CitationResource,
        'citation',
        full=True,
    )
    court = fields.ForeignKey(
        JurisdictionResource,
        'docket__court'
    )
    date_modified = fields.DateTimeField(
        attribute='date_modified',
        null=True,
        default='1750-01-01T00:00:00Z',
        help_text='The last moment when the item was modified. A value  in '
                  'year 1750 indicates the value is unknown'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        resource_name = 'cited-by'
        queryset = Document.objects.all()
        excludes = (
            'html', 'html_lawbox', 'html_with_citations', 'plain_text',
            'supreme_court_db_id',
        )
        include_absolute_url = True
        max_limit = 20
        list_allowed_methods = ['get']
        detail_allowed_methods = []
        filtering = {
            'id': ('exact',),
        }

    def get_object_list(self, request):
        pk = request.GET.get('id')
        if pk:
            return Document.objects.get(pk=pk).citing_opinions.all()
        else:
            # No ID field --> no results.
            return super(CitedByResource, self).get_object_list(request).none()

    def apply_filters(self, request, applicable_filters):
        """The inherited method would attempt to apply filters, but filtering
        is only turned on so we can slip the id parameter through. If this
        function is not overridden and nixed, it attempts normal Django
        filtering, which crashes.

        Thus, do nothing here.
        """
        return self.get_object_list(request)

    def get_resource_uri(self, bundle_or_obj=None,
                         url_name='api_dispatch_list'):
        """Creates a URI like /api/v1/search/$id/
        """
        url_str = '/api/rest/%s/%s/%s/'
        if bundle_or_obj:
            return url_str % (
                self.api_name,
                'opinion',
                bundle_or_obj.obj.id,
            )
        else:
            return ''


class CitesResource(DeprecatedModelResourceWithFieldsFilter):
    citation = fields.ForeignKey(
        CitationResource,
        'citation',
        full=True
    )
    court = fields.ForeignKey(
        JurisdictionResource,
        'docket__court'
    )
    date_modified = fields.DateTimeField(
        attribute='date_modified',
        null=True,
        default='1750-01-01T00:00:00Z',
        help_text='The last moment when the item was modified. A value  in '
                  'year 1750 indicates the value is unknown'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        resource_name = 'cites'
        queryset = Document.objects.all()
        excludes = (
            'html', 'html_lawbox', 'html_with_citations', 'plain_text',
            'supreme_court_db_id',
        )
        include_absolute_url = True
        max_limit = 20
        list_allowed_methods = ['get']
        detail_allowed_methods = []
        filtering = {
            'id': ('exact',),
        }

    def get_object_list(self, request):
        """Get the citation associated with the document ID, then get all the
        items that it is cited by.
        """
        pk = request.GET.get('id')
        if pk:
            return Document.objects.get(pk=pk).opinions_cited.all()
        else:
            # No ID field --> no results.
            return super(CitesResource, self).get_object_list(request).none()

    def apply_filters(self, request, applicable_filters):
        """The inherited method would attempt to apply filters, but filtering
        is only turned on so we can slip the id parameter through. If this
        function is not overridden and nixed, it attempts normal Django
        filtering, which crashes.

        Thus, do nothing here.
        """
        return self.get_object_list(request)

    def get_resource_uri(self, bundle_or_obj=None,
                         url_name='api_dispatch_list'):
        """Creates a URI like /api/v1/search/$id/
        """
        url_str = '/api/rest/%s/%s/%s/'
        if bundle_or_obj:
            return url_str % (
                self.api_name,
                'opinion',
                bundle_or_obj.obj.id,
            )
        else:
            return ''


class SearchResource(DeprecatedModelResourceWithFieldsFilter):
    # Roses to the clever person that makes this introspect the model and
    # removes all this code.
    absolute_url = fields.CharField(
        attribute='absolute_url',
        help_text="The URL on CourtListener for the item.",
        null=True,
    )
    case_name = fields.CharField(
        attribute='caseName',
        help_text="The full name of the case",
        null=True,
    )
    case_number = fields.CharField(
        attribute='caseNumber',
        help_text="The combination of the citation and the docket number.",
        null=True,
    )
    citation = fields.CharField(
        attribute='citation',
        help_text="A concatenated list of all the citations for an opinion.",
        null=True,
    )
    cite_count = fields.IntegerField(
        attribute='citeCount',
        help_text="The number of times this document is cited by other cases",
    )
    court = fields.CharField(
        attribute='court',
        help_text="The name of the court where the document was filed",
        null=True,
    )
    court_id = fields.CharField(
        attribute='court_id',
        help_text='The court where the document was filed',
        null=True,
    )
    date_filed = fields.DateField(
        attribute='dateFiled',
        help_text='The date filed by the court',
        null=True,
    )
    docket_number = fields.CharField(
        attribute='docketNumber',
        help_text='The docket numbers of a case, can be consolidated and quite long',
        null=True,
    )
    download_url = fields.CharField(
        attribute='download_url',
        help_text='The URL on the court website where the document was originally scraped',
        null=True,
    )
    id = fields.CharField(
        attribute='id',
        help_text='The primary key for an opinion.',
    )
    judge = fields.CharField(
        attribute='judge',
        help_text='The judges that brought the opinion as a simple text string',
        null=True,
    )
    local_path = fields.CharField(
        attribute='local_path',
        help_text='The location, relative to MEDIA_ROOT on the CourtListener server, where files are stored',
        null=True,
    )
    score = fields.FloatField(
        attribute='score',
        help_text='The relevance of the result. Will vary from query to query.',
    )
    source = fields.CharField(
        attribute='source',
        help_text='the source of the document, one of: %s' % ', '.join(
            ['%s (%s)' % (t[0], t[1]) for t in
             SOURCES]),
        null=True,
    )
    snippet = fields.CharField(
        attribute='snippet',
        help_text='a snippet as found in search results, utilizing <mark> for highlighting and &hellip; for ellipses',
        null=True,
    )
    status = fields.CharField(
        attribute='status',
        help_text='The precedential status of document, one of: %s' % ', '.join(
            [('stat_%s' % t[1]).replace(' ', '+')
             for t in DOCUMENT_STATUSES]),
        null=True,
    )
    suit_nature = fields.CharField(
        attribute='suitNature',
        help_text="The nature of the suit. For the moment can be codes or laws or whatever",
        null=True,
    )
    text = fields.CharField(
        attribute='text',
        use_in='detail',  # Only shows on the detail page.
        help_text="A concatenated copy of most fields in the item so those fields are available for search."
    )
    timestamp = fields.DateField(
        attribute='timestamp',
        help_text='The moment when an item was indexed by Solr.'
    )

    class Meta:
        authentication = authentication.MultiAuthentication(
            BasicAuthenticationWithUser(realm="courtlistener.com"),
            authentication.SessionAuthentication())
        throttle = PerUserCacheThrottle(throttle_at=1000)
        resource_name = 'search'
        max_limit = 20
        include_absolute_url = True
        allowed_methods = ['get']
        filtering = {
            'q': ('search',),
            'case_name': ('search',),
            'judge': ('search',),
            'stat_': ('boolean',),
            'filed_after': ('date', ),
            'filed_before': ('date',),
            'citation': ('search',),
            'neutral_cite': ('search',),
            'docket_number': ('search',),
            'cited_gt': ('int',),
            'cited_lt': ('int',),
            'court': ('csv',),
        }
        ordering = [
            'dateFiled+desc', 'dateFiled+asc',
            'citeCount+desc', 'citeCount+asc',
            'score+desc',
        ]

    def get_resource_uri(self, bundle_or_obj=None,
                         url_name='api_dispatch_list'):
        """Creates a URI like /api/v1/search/$id/
        """
        url_str = '/api/rest/%s/%s/%s/'
        if bundle_or_obj:
            return url_str % (
                self.api_name,
                'opinion',
                bundle_or_obj.obj.id,
            )
        else:
            return ''

    def get_object_list(self, request=None, **kwargs):
        """Performs the Solr work."""
        main_query = {'caller': 'api_search'}
        try:
            main_query.update(build_main_query(kwargs['cd'],
                                               highlight='text'))
            sl = SolrList(
                main_query=main_query,
                offset=request.GET.get('offset', 0),
                limit=request.GET.get('limit', 20),
                type=kwargs['cd']['type']
            )
        except KeyError:
            sf = forms.SearchForm({'q': "*:*"})
            if sf.is_valid():
                main_query.update(build_main_query(sf.cleaned_data,
                                                   highlight='text'))
            sl = SolrList(
                main_query=main_query,
                offset=request.GET.get('offset', 0),
                limit=request.GET.get('limit', 20),
            )

        return sl

    def obj_get_list(self, bundle, **kwargs):
        search_form = forms.SearchForm(bundle.request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if cd['q'] == '':
                cd['q'] = '*:*'  # Get everything.
            return self.get_object_list(bundle.request, cd=cd)
        else:
            BadRequest("Invalid resource lookup data provided. Unable to "
                       "complete your query.")

    def obj_get(self, bundle, **kwargs):
        search_form = forms.SearchForm(bundle.request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            cd['q'] = 'id:%s' % kwargs['pk']
            return self.get_object_list(bundle.request, cd=cd)[0]
        else:
            BadRequest("Invalid resource lookup data provided. Unable to "
                       "complete your request.")

    def apply_sorting(self, obj_list, options=None):
        """Since we're not using Django Model sorting, we just want to use our
        own, which is already passed into the search form anyway.

        Thus: Do nothing here.
        """
        return obj_list
