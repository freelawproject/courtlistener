import json
import os
import rest_framework_filters as filters

from cl import settings
from cl.api import serializers
from cl.audio.models import Audio
from cl.lib import magic
from cl.lib import search_utils
from cl.lib.api import SolrList
from cl.lib.sunburnt import sunburnt
from cl.search import forms
from cl.search.models import Court, OpinionCluster, Docket, OpinionsCited, \
    Opinion, JURISDICTIONS
from cl.stats import tally_stat

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from rest_framework import viewsets






def annotate_courts_with_counts(courts, court_count_tuples):
    """Solr gives us a response like:

        court_count_tuples = [
            ('ca2', 200),
            ('ca1', 42),
            ...
        ]

    Here we add an attribute to our court objects so they have these values.
    """
    # Convert the tuple to a dict
    court_count_dict = {}
    for court_str, count in court_count_tuples:
        court_count_dict[court_str] = count

    for court in courts:
        court.count = court_count_dict.get(court.pk, 0)

    return courts


def make_court_variable():
    courts = Court.objects.exclude(jurisdiction='T')  # Non-testing courts
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    response = conn.raw_query(
        **search_utils.build_court_count_query()).execute()
    court_count_tuples = response.facet_counts.facet_fields['court_exact']
    courts = annotate_courts_with_counts(courts, court_count_tuples)
    return courts


def court_index(request):
    """Shows the information we have available for the courts."""
    courts = make_court_variable()
    return render_to_response(
        'jurisdictions.html',
        {'courts': courts,
         'private': False},
        RequestContext(request)
    )


def rest_docs(request, version):
    """Show the correct version of the rest docs"""
    courts = make_court_variable()
    court_count = len(courts)
    if version is None:
        version = 'latest'
    return render_to_response(
        'rest-docs-v%s.html' % version,
        {'court_count': court_count,
         'courts': courts,
         'private': False},
        RequestContext(request)
    )


def api_index(request):
    court_count = Court.objects.exclude(
        jurisdiction='T'
    ).count()  # Non-testing courts
    return render_to_response(
        'docs.html',
        {'court_count': court_count,
         'private': False},
        RequestContext(request)
    )


def bulk_data_index(request):
    """Shows an index page for the dumps."""
    courts = make_court_variable()
    court_count = len(courts)
    return render_to_response(
        'bulk-data.html',
        {'court_count': court_count,
         'courts': courts,
         'private': False},
        RequestContext(request)
    )


def serve_pagerank_file(request):
    """Serves the bulk pagerank file from the bulk data directory."""
    file_loc = settings.BULK_DATA_DIR + "external_pagerank"
    file_name = file_loc.split('/')[-1]
    try:
        mimetype = magic.from_file(file_loc, mime=True)
    except IOError:
        raise Http404('Unable to locate external_pagerank file in %s' % settings.BULK_DATA_DIR)
    response = HttpResponse()
    response['X-Sendfile'] = os.path.join(file_loc)
    response['Content-Disposition'] = 'attachment; filename="%s"' % file_name.encode('utf-8')
    response['Content-Type'] = mimetype
    tally_stat('bulk_data.pagerank.served')
    return response


def strip_trailing_zeroes(data):
    """Removes zeroes from the end of the court data

    Some courts only have values through to a certain date, but we don't
    check for that in our queries. Instead, we truncate any zero-values that
    occur at the end of their stats.
    """
    i = len(data) - 1
    while i > 0:
        if data[i][1] == 0:
            i -= 1
        else:
            break

    return data[:i + 1]


def coverage_data(request, version, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """

    if court != 'all':
        court_str = get_object_or_404(Court, pk=court).pk
    else:
        court_str = 'all'
    q = request.GET.get('q')
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    start_year = search_utils.get_court_start_year(conn, court_str)
    response = conn.raw_query(
        **search_utils.build_coverage_query(court_str, start_year, q)
    ).execute()
    counts = response.facet_counts.facet_ranges[0][1][0][1]
    counts = strip_trailing_zeroes(counts)

    # Calculate the totals
    annual_counts = {}
    total_docs = 0
    for date_string, count in counts:
        annual_counts[date_string[:4]] = count
        total_docs += count
    response = {
        'annual_counts': annual_counts,
        'total': total_docs,
    }

    return JsonResponse(json.dumps(response), safe=False)


def deprecated_api(request, v):
    return JsonResponse(
        {
            "meta": {
                "status": "This endpoint is deprecated. Please upgrade to the "
                          "newest version of the API.",
            },
            "objects": []
        },
        safe=False,
        status=410,  # Gone
    )


class CourtFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    position = filters.AllLookupsFilter(name='position')
    start_date = filters.AllLookupsFilter(name='start_date')
    end_date = filters.AllLookupsFilter(name='end_date')

    class Meta:
        model = Court
        fields = (
            'id', 'date_modified', 'in_use', 'has_opinion_scraper',
            'has_oral_argument_scraper', 'position', 'start_date', 'end_date',
            'jurisdiction',
        )


class DocketFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_argued = filters.AllLookupsFilter(name='date_argued')
    date_reargued = filters.AllLookupsFilter(name='date_reargued')
    date_reargument_denied = filters.AllLookupsFilter(name='date_reargument_denied')
    court = filters.RelatedFilter(CourtFilter, name='court')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')

    class Meta:
        model = Docket
        fields = (
            'id', 'blocked',
        )


class AudioFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = Audio
        fields = (
            'id', 'source', 'sha1', 'blocked', 'processing_complete',
        )


class OpinionClusterFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    date_filed = filters.AllLookupsFilter(name='date_filed')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = OpinionCluster
        fields = (
            'id', 'per_curiam', 'citation_id', 'citation_count', 'scdb_id',
            'scdb_decision_direction', 'scdb_votes_majority',
            'scdb_votes_minority', 'source', 'precedential_status', 'blocked',
        )


class OpinionFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    cluster = filters.RelatedFilter(OpinionClusterFilter, name='cluster')

    class Meta:
        model = Opinion
        fields = (
            'id', 'type', 'sha1', 'extracted_by_ocr'
        )


class DocketViewSet(viewsets.ModelViewSet):
    queryset = Docket.objects.all()
    serializer_class = serializers.DocketSerializer
    filter_class = DocketFilter


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.exclude(jurisdiction='T')
    serializer_class = serializers.CourtSerializer
    filter_class = CourtFilter


class AudioViewSet(viewsets.ModelViewSet):
    queryset = Audio.objects.all()
    serializer_class = serializers.AudioSerializer
    filter_class = AudioFilter


class OpinionClusterViewSet(viewsets.ModelViewSet):
    queryset = OpinionCluster.objects.all()
    serializer_class = serializers.OpinionClusterSerializer
    filter_class = OpinionClusterFilter


class OpinionViewSet(viewsets.ModelViewSet):
    queryset = Opinion.objects.all()
    serializer_class = serializers.OpinionSerializer
    filter_class = OpinionFilter


class OpinionsCitedViewSet(viewsets.ModelViewSet):
    queryset = OpinionsCited.objects.all()
    serializer_class = serializers.OpinionsCitedSerializer
    filter_fields = ('id',)


def get_object_list(request=None, **kwargs):
    """Perform the Solr work"""
    main_query = {'caller': 'api_search'}
    try:
        main_query.update(search_utils.build_main_query(
            kwargs['cd'],
            highlight='text'
        ))
        sl = SolrList(
            main_query=main_query,
            offset=request.GET.get('offset', 0),
            limit=request.GET.get('limit', 20),
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
            offset=request.GET.get('offset', 0),
            limit=request.GET.get('limit', 20),
        )
    return sl


def search_list(request):
    if request.method == 'GET':
        search_form = forms.SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if cd['q'] == '':
                cd['q'] = '*:*'  # Get everything
            sl = get_object_list(request, cd=cd)
            serializer = serializers.SearchResultSerializer(sl, many=True)
            return JsonResponse(serializer.data)
        else:
            # XXX: Throw some kind of warning here
            pass




class CourtFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    position = filters.AllLookupsFilter(name='position')
    start_date = filters.AllLookupsFilter(name='start_date')
    end_date = filters.AllLookupsFilter(name='end_date')

    class Meta:
        model = Court
        fields = (
            'id', 'date_modified', 'in_use', 'has_opinion_scraper',
            'has_oral_argument_scraper', 'position', 'start_date', 'end_date',
            'jurisdiction',
        )


class DocketFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_argued = filters.AllLookupsFilter(name='date_argued')
    date_reargued = filters.AllLookupsFilter(name='date_reargued')
    date_reargument_denied = filters.AllLookupsFilter(name='date_reargument_denied')
    court = filters.RelatedFilter(CourtFilter, name='court')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')

    class Meta:
        model = Docket
        fields = (
            'id', 'blocked',
        )


class AudioFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = Audio
        fields = (
            'id', 'source', 'sha1', 'blocked', 'processing_complete',
        )


class OpinionClusterFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    date_filed = filters.AllLookupsFilter(name='date_filed')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = OpinionCluster
        fields = (
            'id', 'per_curiam', 'citation_id', 'citation_count', 'scdb_id',
            'scdb_decision_direction', 'scdb_votes_majority',
            'scdb_votes_minority', 'source', 'precedential_status', 'blocked',
        )


class OpinionFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    cluster = filters.RelatedFilter(OpinionClusterFilter, name='cluster')

    class Meta:
        model = Opinion
        fields = (
            'id', 'type', 'sha1', 'extracted_by_ocr'
        )


class DocketViewSet(viewsets.ModelViewSet):
    queryset = Docket.objects.all()
    serializer_class = serializers.DocketSerializer
    filter_class = DocketFilter


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.exclude(jurisdiction='T')
    serializer_class = serializers.CourtSerializer
    filter_class = CourtFilter


class AudioViewSet(viewsets.ModelViewSet):
    queryset = Audio.objects.all()
    serializer_class = serializers.AudioSerializer
    filter_class = AudioFilter


class OpinionClusterViewSet(viewsets.ModelViewSet):
    queryset = OpinionCluster.objects.all()
    serializer_class = serializers.OpinionClusterSerializer
    filter_class = OpinionClusterFilter


class OpinionViewSet(viewsets.ModelViewSet):
    queryset = Opinion.objects.all()
    serializer_class = serializers.OpinionSerializer
    filter_class = OpinionFilter


class OpinionsCitedViewSet(viewsets.ModelViewSet):
    queryset = OpinionsCited.objects.all()
    serializer_class = serializers.OpinionsCitedSerializer
    filter_fields = ('id',)


def get_object_list(request=None, **kwargs):
    """Perform the Solr work"""
    main_query = {'caller': 'api_search'}
    try:
        main_query.update(search_utils.build_main_query(
            kwargs['cd'],
            highlight='text'
        ))
        sl = SolrList(
            main_query=main_query,
            offset=request.GET.get('offset', 0),
            limit=request.GET.get('limit', 20),
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
            offset=request.GET.get('offset', 0),
            limit=request.GET.get('limit', 20),
        )
    return sl


def search_list(request):
    if request.method == 'GET':
        search_form = forms.SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if cd['q'] == '':
                cd['q'] = '*:*'  # Get everything
            sl = get_object_list(request, cd=cd)
            serializer = serializers.SearchResultSerializer(sl, many=True)
            return JsonResponse(serializer.data)
        else:
            # XXX: Throw some kind of warning here
            pass


