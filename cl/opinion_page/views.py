from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache

from cl.lib import search_utils
from cl.lib.encode_decode import ascii_to_num
from cl.lib.string_utils import trunc
from cl.search.models import Docket, OpinionCluster
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite


def view_docket(request, pk, _):
    docket = get_object_or_404(Docket, pk=pk)
    return render_to_response(
        'view_docket.html',
        {'docket': docket,
         'private': docket.blocked},
        RequestContext(request),
    )


@never_cache
def view_opinion(request, pk, _):
    """Using the ID, return the document.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, document, title and favorite information
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = '%s, %s' % (
        trunc(cluster.case_name, 100),
        cluster.citation_string,
    )
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(
            cluster_id=cluster.pk,
            user=request.user,
        )
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                'cluster_id': cluster.pk,
                'name': trunc(cluster.case_name, 100, ellipsis='...'),
            }
        )

    # get most influential opinions that cite this opinion
    citing_clusters = OpinionCluster.objects.filter(
        sub_opinions__in=cluster.sub_opinions.all()
    ).order_by(
        '-citation_count',
        '-date_filed',
    )[:5]

    authorities_count = 0
    top_authorities = None
    for sub_opinion in cluster.sub_opinions.all():
        authorities_count += sub_opinion.opinions_cited.all().count()
        if sub_opinion.type == 'lead' or sub_opinion.type == 'combined':
            # At first, all citations will be between majority or combined
            # sub_opinions.
            top_authorities = sub_opinion.opinions_cited.all().select_related(
                'cluster').order_by('cluster__case_name')[:5]

    return render_to_response(
        'view_opinion.html',
        {'title': title,
         'citation_string': citation_string,
         'cluster': cluster,
         'favorite_form': favorite_form,
         'get_string': get_string,
         'private': cluster.blocked,
         'citing_clusters': citing_clusters,
         'top_authorities': top_authorities,
         'authorities_count': authorities_count},
        RequestContext(request)
    )


def view_opinion_citations(request, pk, _):
    doc = get_object_or_404(Document, pk=pk)
    title = '%s, %s' % (
        trunc(doc.case_name, 100),
        cluster.citation_string
    )

    # Get list of cases we cite, ordered by citation count
    citing_opinions = doc.citation.citing_opinions.select_related(
        'citation', 'docket__court').order_by('-citation_count', '-date_filed')

    paginator = Paginator(citing_opinions, 20, orphans=2)
    page = request.GET.get('page')
    try:
        citing_opinions = paginator.page(page)
    except (TypeError, PageNotAnInteger):
        # TypeError can be removed in Django 1.4, where it properly will be
        # caught upstream.
        citing_opinions = paginator.page(1)
    except EmptyPage:
        citing_opinions = paginator.page(paginator.num_pages)

    private = False
    if doc.blocked:
        private = True
    else:
        for case in citing_opinions.object_list:
            if case.blocked:
                private = True
                break

    return render_to_response('view_opinion_citations.html',
                              {'title': title,
                               'doc': doc,
                               'private': private,
                               'citing_opinions': citing_opinions},
                              RequestContext(request))


def view_authorities(request, pk, _):
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = '%s, %s' % (
        trunc(cluster.case_name, 100),
        cluster.citation_string
    )

    # Ordering is by case name is the norm.
    authorities = cluster.opinions_cited.all().select_related(
        'document').order_by('case_name')

    private = False
    if cluster.blocked:
        private = True
    else:
        for case in authorities:
            if case.parent_documents.all()[0].blocked:
                private = True
                break

    return render_to_response('view_opinion_authorities.html',
                              {'title': title,
                               'doc': doc,
                               'private': private,
                               'authorities': authorities},
                              RequestContext(request))


def redirect_opinion_pages(request, pk, slug):
    pk = ascii_to_num(pk)
    path = reverse('view_case', args=[pk, slug])
    if request.path.endswith('/authorities/'):
        path += 'authorities/'
    elif request.path.endswith('/cited-by/'):
        path += 'cited-by/'
    if request.META['QUERY_STRING']:
        path = '%s?%s' % (path, request.META['QUERY_STRING'])
    return HttpResponsePermanentRedirect(path)


def redirect_cited_by_feeds(request, pk):
    pk = ascii_to_num(pk)
    path = reverse('cited_by_feed', kwargs={'doc_id': pk})
    return HttpResponsePermanentRedirect(path)

