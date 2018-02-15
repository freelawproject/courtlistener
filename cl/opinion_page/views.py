from itertools import groupby

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import F, Q, Prefetch
from django.http import HttpResponseRedirect
from django.http.response import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.status import HTTP_404_NOT_FOUND

from cl.citations.find_citations import get_citations
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.lib import search_utils, sunburnt
from cl.lib.bot_detector import is_bot
from cl.lib.import_lib import map_citations_to_models
from cl.lib.model_helpers import suppress_autotime
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted
from cl.lib.search_utils import make_get_string
from cl.lib.string_utils import trunc
from cl.people_db.models import AttorneyOrganization, Role
from cl.opinion_page.forms import CitationRedirectorForm, DocketEntryFilterForm
from cl.recap.constants import COURT_TIMEZONES
from cl.search.models import Docket, OpinionCluster, RECAPDocument


def redirect_docket_recap(request, court, pacer_case_id):
    docket = get_object_or_404(Docket, pacer_case_id=pacer_case_id,
                               court=court)
    return HttpResponseRedirect(reverse('view_docket', args=[docket.pk,
                                                             docket.slug]))


@ratelimit_if_not_whitelisted
def view_docket(request, pk, slug):
    docket = get_object_or_404(Docket, pk=pk)
    if not is_bot(request):
        with suppress_autotime(docket, ['date_modified']):
            cached_count = docket.view_count
            docket.view_count = F('view_count') + 1
            docket.save()
            docket.view_count = cached_count + 1

    try:
        fave = Favorite.objects.get(docket_id=docket.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'docket_id': docket.pk,
            'name': trunc(best_case_name(docket), 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    de_list = docket.docket_entries.all().prefetch_related('recap_documents')
    form = DocketEntryFilterForm(request.GET)
    if form.is_valid():
        cd = form.cleaned_data
        if cd.get('entry_gte'):
            de_list = de_list.filter(entry_number__gte=cd['entry_gte'])
        if cd.get('entry_lte'):
            de_list = de_list.filter(entry_number__lte=cd['entry_lte'])
        if cd.get('filed_after'):
            de_list = de_list.filter(date_filed__gte=cd['filed_after'])
        if cd.get('filed_before'):
            de_list = de_list.filter(date_filed__lte=cd['filed_before'])
        if cd.get('order_by') == DocketEntryFilterForm.DESCENDING:
            de_list = de_list.order_by('-entry_number')

    paginator = Paginator(de_list, 100, orphans=5)
    page = request.GET.get('page')
    try:
        docket_entries = paginator.page(page)
    except PageNotAnInteger:
        docket_entries = paginator.page(1)
    except EmptyPage:
        docket_entries = paginator.page(paginator.num_pages)

    return render(request, 'view_docket.html', {
        'docket': docket,
        'parties': docket.parties.exists(),  # Needed to show/hide parties tab.
        'docket_entries': docket_entries,
        'form': form,
        'favorite_form': favorite_form,
        'get_string': make_get_string(request),
        'timezone': COURT_TIMEZONES.get(docket.court_id, 'US/Eastern'),
        'private': docket.blocked,
    })


@ratelimit_if_not_whitelisted
def view_parties(request, docket_id, slug):
    """Show the parties and attorneys tab on the docket."""
    docket = get_object_or_404(Docket, pk=docket_id, slug=slug)
    try:
        fave = Favorite.objects.get(docket_id=docket.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'docket_id': docket.pk,
            'name': trunc(best_case_name(docket), 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    # We work with this data at the level of party_types so that we can group
    # the parties by this field. From there, we do a whole mess of prefetching,
    # which reduces the number of queries needed for this down to four instead
    # of potentially thousands (good times!)
    party_types = docket.party_types.select_related('party').prefetch_related(
        Prefetch('party__roles',
                 queryset=Role.objects.filter(
                     docket=docket
                 ).order_by(
                     'attorney_id', 'role', 'date_action'
                 ).select_related(
                     'attorney'
                 ).prefetch_related(
                     Prefetch('attorney__organizations',
                              queryset=AttorneyOrganization.objects.filter(
                                  attorney_organization_associations__docket=docket),
                              to_attr='firms_in_docket')
                 ))
    ).order_by('name', 'party__name')

    parties = []
    for party_type_name, party_types in groupby(party_types, lambda x: x.name):
        party_types = list(party_types)
        parties.append({
            'party_type_name': party_type_name,
            'party_type_objects': party_types
        })

    return render(request, 'docket_parties.html', {
        'docket': docket,
        'parties': parties,
        'favorite_form': favorite_form,
        'timezone': COURT_TIMEZONES.get(docket.court_id, 'US/Eastern'),
        'private': docket.blocked,
    })


@ratelimit_if_not_whitelisted
def view_recap_document(request, docket_id=None, doc_num=None,  att_num=None,
                        slug=''):
    """This view can either load an attachment or a regular document,
    depending on the URL pattern that is matched.
    """
    item = get_object_or_404(
        RECAPDocument,
        docket_entry__docket__id=docket_id,
        document_number=doc_num,
        attachment_number=att_num,
    )
    title = '%sDocument #%s%s in %s' % (
        '%s &ndash; ' % item.description if item.description else '',
        item.document_number,
        ', Attachment #%s' % item.attachment_number if
        item.document_type == RECAPDocument.ATTACHMENT else '',
        best_case_name(item.docket_entry.docket),
    )
    try:
        fave = Favorite.objects.get(recap_doc_id=item.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'recap_doc_id': item.pk,
            'name': trunc(title, 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    return render(request, 'recap_document.html', {
        'document': item,
        'title': title,
        'favorite_form': favorite_form,
        'private': True,  # Always True for RECAP docs.
    })


@never_cache
@ratelimit_if_not_whitelisted
def view_opinion(request, pk, _):
    """Using the cluster ID, return the cluster of opinions.

    We also test if the cluster ID is a favorite for the user, and send data
    if needed. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, cluster, title and favorite information
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = ', '.join([s for s in [
        trunc(best_case_name(cluster), 100),
        cluster.citation_string,
    ] if s.strip()])
    has_downloads = False
    for sub_opinion in cluster.sub_opinions.all():
        if sub_opinion.local_path or sub_opinion.download_url:
            has_downloads = True
            break
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(cluster_id=cluster.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'cluster_id': cluster.pk,
            'name': trunc(best_case_name(cluster), 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    # Get the citing results from Solr for speed.
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    q = {
        'q': 'cites:({ids})'.format(
            ids=' OR '.join([str(pk) for pk in
                             (cluster.sub_opinions
                              .values_list('pk', flat=True))])
        ),
        'rows': 5,
        'start': 0,
        'sort': 'citeCount desc',
        'caller': 'view_opinion',
    }
    citing_clusters = conn.raw_query(**q).execute()

    return render(request, 'view_opinion.html', {
        'title': title,
        'cluster': cluster,
        'has_downloads': has_downloads,
        'favorite_form': favorite_form,
        'get_string': get_string,
        'private': cluster.blocked,
        'citing_clusters': citing_clusters,
        'top_authorities': cluster.authorities[:5],
    })


@ratelimit_if_not_whitelisted
def view_authorities(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)

    return render(request, 'view_opinion_authorities.html', {
        'title': '%s, %s' % (
            trunc(best_case_name(cluster), 100),
            cluster.citation_string
        ),
        'cluster': cluster,
        'private': cluster.blocked or cluster.has_private_authority,
        'authorities': cluster.authorities.order_by('case_name'),
    })


@ratelimit_if_not_whitelisted
def cluster_visualizations(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    return render(request, 'view_opinion_visualizations.html', {
        'title': '%s, %s' % (
            trunc(best_case_name(cluster), 100),
            cluster.citation_string
        ),
        'cluster': cluster,
        'private': cluster.blocked or cluster.has_private_authority,
    })


def citation_redirector(request, reporter=None, volume=None, page=None):
    """Take a citation URL and use it to redirect the user to the canonical page
    for that citation.

    This uses the same infrastructure as the thing that identifies citations in
    the text of opinions.
    """
    if request.method == 'POST':
        form = CitationRedirectorForm(request.POST)
        if form.is_valid():
            # Redirect to the page with the right values
            cd = form.cleaned_data
            return HttpResponseRedirect(
                reverse('citation_redirector', kwargs=cd)
            )
        else:
            # Error in form, somehow.
            return render(request, 'citation_redirect_info_page.html', {
                'show_homepage': True,
                'form': form,
                'private': True
            })
    else:
        if all(_ is None for _ in (reporter, volume, page)):
            # No parameters. Show the standard page.
            form = CitationRedirectorForm()
            return render(request, 'citation_redirect_info_page.html', {
                'show_homepage': True,
                'form': form,
                'private': False,
            })

        else:
            # We have a citation. Look it up, redirect the user or show
            # disambiguation.
            citation_str = " ".join([volume, reporter, page])
            try:
                citation = get_citations(citation_str)[0]
                citation_str = citation.base_citation()  # Corrects typos/variations.
                lookup_fields = [map_citations_to_models([citation]).keys()[0]]
            except IndexError:
                # Unable to disambiguate the citation. Try looking in *all*
                # citation fields.
                lookup_fields = OpinionCluster().citation_fields

            # We were able to get a match, expand it if it's a federal/state
            # match.
            if (len(lookup_fields) == 1 and
                    lookup_fields[0] == 'federal_cite_one'):
                lookup_fields = ['federal_cite_one', 'federal_cite_two',
                                 'federal_cite_three']
            elif (len(lookup_fields) == 1 and
                    lookup_fields[0] == 'state_cite_one'):
                lookup_fields = ['state_cite_one', 'state_cite_two',
                                 'state_cite_three']
            q = Q()
            for lookup_field in lookup_fields:
                q |= Q(**{lookup_field: citation_str})
            clusters = OpinionCluster.objects.filter(q)

            # Show the correct page....
            if clusters.count() == 0:
                # No results for an otherwise valid citation.
                return render(
                    request,
                    'citation_redirect_info_page.html',
                    {
                        'none_found': True,
                        'citation_str': citation_str,
                        'private': True,
                    },
                    status=HTTP_404_NOT_FOUND,
                )

            elif clusters.count() == 1:
                # Total success. Redirect to correct location.
                return HttpResponseRedirect(
                    clusters[0].get_absolute_url()
                )

            elif clusters.count() > 1:
                # Multiple results. Show them.
                return render(request, 'citation_redirect_info_page.html', {
                    'too_many': True,
                    'citation_str': citation_str,
                    'clusters': clusters,
                    'private': True,
                })


@ensure_csrf_cookie
def block_item(request):
    """Block an item from search results using AJAX"""
    if request.is_ajax() and request.user.is_superuser:
        obj_type = request.POST['type']
        pk = request.POST['id']
        if obj_type == 'docket':
            # Block the docket
            d = get_object_or_404(Docket, pk=pk)
            d.blocked = True
            d.date_blocked = now()
            d.save()
        elif obj_type == 'cluster':
            # Block the cluster and the docket
            cluster = get_object_or_404(OpinionCluster, pk=pk)
            cluster.blocked = True
            cluster.date_blocked = now()
            cluster.save(index=False)
            cluster.docket.blocked = True
            cluster.docket.date_blocked = now()
            cluster.docket.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request",
        )
