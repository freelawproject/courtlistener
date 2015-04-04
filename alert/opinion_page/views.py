from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache

from alert.lib import search_utils
from alert.lib.encode_decode import ascii_to_num
from alert.lib.string_utils import trunc
from alert.search.models import Document, Docket
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite


def make_citation_string(doc):
    """Make a citation string, joined by commas

    This function creates a series of citations separated by commas that can be
    listed as meta data for an opinion. The order of the items in this list
    follows BlueBook order, so our citations aren't just willy nilly.
    """
    cites = [doc.citation.neutral_cite, doc.citation.federal_cite_one,
             doc.citation.federal_cite_two, doc.citation.federal_cite_three,
             doc.citation.specialty_cite_one, doc.citation.state_cite_regional,
             doc.citation.state_cite_one, doc.citation.state_cite_two,
             doc.citation.state_cite_three, doc.citation.westlaw_cite,
             doc.citation.lexis_cite]
    citation_string = ', '.join([cite for cite in cites if cite])
    return citation_string


def view_docket(request, pk, _):
    docket = get_object_or_404(Docket, pk=pk)
    return render_to_response(
        'casepage/view_docket.html',
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
    doc = get_object_or_404(Document, pk=pk)
    citation_string = make_citation_string(doc)
    title = '%s, %s' % (trunc(doc.citation.case_name, 100), citation_string)
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(doc_id=doc.pk, users__user=request.user)
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                'doc_id': doc.pk,
                'name': trunc(doc.citation.case_name, 100, ellipsis='...'),
            }
        )

    # get most influential opinions that cite this opinion
    cited_by_trunc = doc.citation.citing_opinions.select_related(
        'citation').order_by('-citation_count', '-date_filed')[:5]

    authorities_trunc = doc.cases_cited.all().select_related(
        'document').order_by('case_name')[:5]
    authorities_count = doc.cases_cited.all().count()

    return render_to_response(
        'casepage/view_opinion.html',
        {'title': title,
         'citation_string': citation_string,
         'doc': doc,
         'favorite_form': favorite_form,
         'get_string': get_string,
         'private': doc.blocked,
         'cited_by_trunc': cited_by_trunc,
         'authorities_trunc': authorities_trunc,
         'authorities_count': authorities_count},
        RequestContext(request)
    )


def view_opinion_citations(request, pk, _):
    doc = get_object_or_404(Document, pk=pk)
    title = '%s, %s' % (
        trunc(doc.citation.case_name, 100), make_citation_string(doc))

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

    return render_to_response('casepage/view_opinion_citations.html',
                              {'title': title,
                               'doc': doc,
                               'private': private,
                               'citing_opinions': citing_opinions},
                              RequestContext(request))


def view_authorities(request, pk, _):
    doc = get_object_or_404(Document, pk=pk)
    title = '%s, %s' % (
        trunc(doc.citation.case_name, 100), make_citation_string(doc))

    # Ordering is by case name is the norm.
    authorities = doc.cases_cited.all().select_related(
        'document').order_by('case_name')

    private = False
    if doc.blocked:
        private = True
    else:
        for case in authorities:
            if case.parent_documents.all()[0].blocked:
                private = True
                break

    return render_to_response('casepage/view_opinion_authorities.html',
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

