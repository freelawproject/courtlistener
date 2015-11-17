from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache

from cl.citations.find_citations import get_citations
from cl.lib import search_utils
from cl.lib.encode_decode import ascii_to_num
from cl.lib.import_lib import map_citations_to_models
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
            'favorite_form': favorite_form,
            'get_string': get_string,
            'private': cluster.blocked,
            'citing_clusters': cluster.citing_clusters[:5],
            'top_authorities': cluster.authorities[:5],
        },
        RequestContext(request)
    )


def view_authorities(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)

    return render_to_response(
        'view_opinion_authorities.html',
        {
            'title': '%s, %s' % (
                trunc(cluster.case_name, 100),
                cluster.citation_string
            ),
            'cluster': cluster,
            'private': cluster.blocked or cluster.has_private_authority,
            'authorities': cluster.authorities.order_by('case_name'),
        },
        RequestContext(request)
    )


def cluster_visualizations(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    return render_to_response(
        'view_opinion_visualizations.html',
        {
            'title': '%s, %s' % (
                trunc(cluster.case_name, 100),
                cluster.citation_string
            ),
            'cluster': cluster,
            'private': cluster.blocked or cluster.has_private_authority,
        },
        RequestContext(request)
    )


def citation_redirector(request, reporter, volume, page):
    """Take a citation URL and use it to redirect the user to the canonical page
    for that citation.

    This uses the same infrastructure as the thing that identifies citations in
    the text of opinions.
    """
    citation_str = " ".join([volume, reporter, page])
    try:
        citation = get_citations(citation_str)[0]
        citation_str = citation.base_citation()  # Corrects typos/variations.
        lookup_fields = [map_citations_to_models([citation]).keys()[0]]
    except IndexError:
        # Unable to disambiguate the citation. Try looking in *all* citation
        # fields.
        lookup_fields = OpinionCluster().citation_fields

    # We were able to get a match, expand it if it's a federal/state match.
    if len(lookup_fields) == 1 and lookup_fields[0] == 'federal_cite_one':
        lookup_fields = ['federal_cite_one', 'federal_cite_two',
                         'federal_cite_three']
    elif len(lookup_fields) == 1 and lookup_fields[0] == 'state_cite_one':
        lookup_fields = ['state_cite_one', 'state_cite_two',
                         'state_cite_three']
    q = Q()
    for lookup_field in lookup_fields:
        q |= Q(**{lookup_field: citation_str})
    clusters = OpinionCluster.objects.filter(q)

    # Show the correct page....
    if clusters.count() == 0:
        # No results for an otherwise valid citation.
        return render_to_response(
            'citation_redirect_info_page.html',
            {
                'none_found': True,
                'citation_str': citation_str,
                'private': True,
            },
            RequestContext(request),
            status=404,
        )

    elif clusters.count() == 1:
        # Total success. Redirect to correct location.
        return HttpResponsePermanentRedirect(
            clusters[0].get_absolute_url()
        )

    elif clusters.count() > 1:
        # Multiple results. Show them.
        return render_to_response(
            'citation_redirect_info_page.html',
            {
                'too_many': True,
                'citation_str': citation_str,
                'clusters': clusters,
                'private': True,
            },
            RequestContext(request),
            status=300,
        )


def redirect_opinion_pages(request, pk, slug):
    # Handles the old /$court/$ascii/$slug/(authorities)? format. /cited-by/
    # is handled elsewhere since that page has now been through additional
    # movements.
    pk = ascii_to_num(pk)
    path = reverse('view_case', args=[pk, slug])
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
