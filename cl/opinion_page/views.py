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
    """Using the cluster ID, return the cluster of opinions.

    We also test if the cluster ID is a favorite for the user, and send data
    if needed. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, cluster, title and favorite information
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = '%s, %s' % (
        trunc(cluster.case_name, 100),
        cluster.citation_string,
    )
    get_string = search_utils.make_get_string(request)
    or_joined_sub_ids = ' OR '.join([str(sub_opinion.pk) for sub_opinion in
                                     cluster.sub_opinions.all()])

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

    return render_to_response(
        'view_opinion.html',
        {
            'title': title,
            'cluster': cluster,
            'or_joined_sub_ids': or_joined_sub_ids,
            'favorite_form': favorite_form,
            'get_string': get_string,
            'private': cluster.blocked,
            'citing_clusters': cluster.citing_clusters[:5],
            'top_authorities': cluster.authority_data['authorities'][:5],
        },
        RequestContext(request)
    )


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


def redirect_opinion_pages(request, pk):
    # Handles the old /$court/$ascii/$slug/(authorities)? format. /cited-by/
    # is handled elsewhere since that page has now been through additional
    # movements.
    pk = ascii_to_num(pk)
    path = reverse('view_case', args=[pk])
    if request.path.endswith('/authorities/'):
        path += 'authorities/'
    if request.META['QUERY_STRING']:
        path = '%s?%s' % (path, request.META['QUERY_STRING'])
    return HttpResponsePermanentRedirect(path)


def redirect_cited_by_feeds(request, pk):
    try:
        int(pk)
    except ValueError:
        # Cannot cast to int, must be ascii.
        pk = ascii_to_num(pk)
    return HttpResponsePermanentRedirect('/feed/search/?q=cites%%3A%s' % pk)

def redirect_cited_by_page(request, pk):
    try:
        int(pk)
    except ValueError:
        # Cannot cast to int, must be ascii
        pk = ascii_to_num(pk)
    return HttpResponsePermanentRedirect('/?q=cites%%3A%s' % pk)
