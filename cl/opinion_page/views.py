from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import F, Q
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.http.response import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from cl.citations.find_citations import get_citations
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.lib import search_utils, sunburnt
from cl.lib.bot_detector import is_bot
from cl.lib.encode_decode import ascii_to_num
from cl.lib.import_lib import map_citations_to_models
from cl.lib.search_utils import make_get_string
from cl.lib.string_utils import trunc
from cl.opinion_page.forms import CitationRedirectorForm, DocketEntryFilterForm
from cl.search.models import Docket, OpinionCluster, DocketEntry, RECAPDocument


def view_docket(request, pk, _):
    docket = get_object_or_404(Docket, pk=pk)
    if not is_bot(request):
        docket.view_count = F('view_count') + 1
        docket.save()

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

    de_list = docket.docket_entries.all()
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

    paginator = Paginator(de_list, 500, orphans=25)
    page = request.GET.get('page')
    try:
        docket_entries = paginator.page(page)
    except PageNotAnInteger:
        docket_entries = paginator.page(1)
    except EmptyPage:
        docket_entries = paginator.page(paginator.num_pages)

    return render(request, 'view_docket.html', {
        'docket': docket,
        'docket_entries': docket_entries,
        'form': form,
        'favorite_form': favorite_form,
        'get_string': make_get_string(request),
        'private': docket.blocked,
    })


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


def ajax_get_recap_documents_and_attachments(request, pk):
    """This is the ajax view that powers the modals on the docket
    page when a docket entry is clicked.
    """
    docs = DocketEntry.objects.get(pk=pk).recap_documents.all()

    j = {'attachments': [], 'documents': [], 'item_count': 0}
    for doc in docs:
        date_upload = getattr(doc, 'date_upload', "")
        if date_upload:
            date_upload = date_upload.isoformat()

        d = {
            'date_upload': date_upload,
            'document_number': doc.document_number,
            'attachment_number': doc.attachment_number,
            'is_available': doc.is_available,
            'pacer_url': doc.pacer_url or '',
            'filepath_local': doc.filepath_local.name,
            'absolute_url': doc.get_absolute_url(),
            'description': doc.description,
        }

        if doc.document_type == RECAPDocument.PACER_DOCUMENT:
            j['documents'].append(d)
        elif doc.document_type == RECAPDocument.ATTACHMENT:
            j['attachments'].append(d)
        j['item_count'] += 1

    return JsonResponse(
        j,
        safe=False,
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
        trunc(best_case_name(cluster), 100),
        cluster.citation_string,
    )
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
        'favorite_form': favorite_form,
        'get_string': get_string,
        'private': cluster.blocked,
        'citing_clusters': citing_clusters,
        'top_authorities': cluster.authorities[:5],
    })


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
                return render(request, 'citation_redirect_info_page.html', {
                    'none_found': True,
                    'citation_str': citation_str,
                    'private': True,
                })

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
