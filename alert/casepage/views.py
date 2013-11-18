import re
from alert import settings
from alert.lib.encode_decode import ascii_to_num
from alert.lib import magic
from alert.lib import search_utils
from alert.lib.string_utils import trunc
from alert.search.models import Court, Document
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache

import os


def make_citation_string(doc):
    """Make a citation string, joined by commas

    This function creates a series of citations separated by commas that can be listed as meta data for a document. The
    order of the items in this list follows BlueBook order, so our citations aren't just willy nilly.
    """
    cites = [doc.citation.neutral_cite, doc.citation.federal_cite_one, doc.citation.federal_cite_two,
             doc.citation.federal_cite_three, doc.citation.specialty_cite_one, doc.citation.state_cite_regional,
             doc.citation.state_cite_one, doc.citation.state_cite_two, doc.citation.state_cite_three,
             doc.citation.westlaw_cite, doc.citation.lexis_cite]
    citation_string = ', '.join([cite for cite in cites if cite])
    return citation_string


@never_cache
def view_case(request, court, pk, casename):
    """Take a court and an ID, and return the document.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, document, title and favorite information
    doc = get_object_or_404(Document, pk=ascii_to_num(pk))
    ct = get_object_or_404(Court, pk=court)
    citation_string = make_citation_string(doc)
    title = '%s, %s' % (trunc(doc.citation.case_name, 100), citation_string)
    get_string = search_utils.make_get_string(request)

    try:
        # Get the favorite, if possible
        fave = Favorite.objects.get(doc_id=doc.pk, users__user=request.user)
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={'doc_id': doc.pk,
            'name': doc.citation.case_name})

    # get most influential cases that cite this case
    cited_by_trunc = doc.citation.citing_cases.select_related(
          'citation').order_by('-citation_count', '-date_filed')[:5]

    authorities_trunc = doc.cases_cited.all().select_related(
        'document').order_by('-parent_documents__date_filed', '-parent_documents__citation_count', )[:5]
    authorities_count = doc.cases_cited.all().count()

    return render_to_response(
        'view_case.html',
        {'title': title,
         'citation_string': citation_string,
         'doc': doc,
         'court': ct,
         'favorite_form': favorite_form,
         'get_string': get_string,
         'private': doc.blocked,
         'cited_by_trunc': cited_by_trunc,
         'authorities_trunc': authorities_trunc,
         'authorities_count': authorities_count},
        RequestContext(request)
    )


def view_case_citations(request, pk, case_name):
    pk = ascii_to_num(pk)

    # Look up the document, title
    doc = get_object_or_404(Document, pk=pk)
    title = '%s, %s' % (trunc(doc.citation.case_name, 100), make_citation_string(doc))

    # Get list of cases we cite, ordered by citation count
    citing_cases = doc.citation.citing_cases.select_related(
            'citation', 'court').order_by('-citation_count', '-date_filed')

    paginator = Paginator(citing_cases, 20, orphans=2)
    page = request.GET.get('page')
    try:
        citing_cases = paginator.page(page)
    except (TypeError, PageNotAnInteger):
        # TypeError can be removed in Django 1.4, where it properly will be
        # caught upstream.
        citing_cases = paginator.page(1)
    except EmptyPage:
        citing_cases = paginator.page(paginator.num_pages)

    private = False
    if doc.blocked:
        private = True
    else:
        for case in citing_cases.object_list:
            if case.blocked:
                private = True
                break

    return render_to_response('view_case_citations.html',
                              {'title': title,
                               'doc': doc,
                               'private': private,
                               'citing_cases': citing_cases},
                              RequestContext(request))


def view_authorities(request, pk, case_name):
    pk = ascii_to_num(pk)

    doc = get_object_or_404(Document, pk=pk)
    title = '%s, %s' % (trunc(doc.citation.case_name, 100), make_citation_string(doc))

    # Ordering is by date, then citation count
    authorities = doc.cases_cited.all().select_related(
        'document').order_by('-parent_documents__date_filed', '-parent_documents__citation_count', )

    private = False
    if doc.blocked:
        private = True
    else:
        for case in authorities:
            if case.parent_documents.all()[0].blocked:
                private = True
                break

    return render_to_response('view_case_authorities.html',
                              {'title': title,
                               'doc': doc,
                               'private': private,
                               'authorities': authorities},
                              RequestContext(request))


def serve_static_file(request, file_path=''):
    """Sends a static file to a user.

    This serves up the static case files such as the PDFs in a way that can be
    blocked from search engines if necessary. We do four things:
     - Look up the document associated with the filepath
     - Check if it's blocked
     - If blocked, we set the x-robots-tag HTTP header
     - Serve up the file using Apache2's xsendfile
    """
    doc = get_object_or_404(Document, local_path=file_path)
    file_name = file_path.split('/')[-1]
    file_loc = os.path.join(settings.MEDIA_ROOT, file_path.encode('utf-8'))
    try:
        mimetype = magic.from_file(file_loc, mime=True)
    except IOError:
        raise Http404
    response = HttpResponse()
    if doc.blocked:
        response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    response['X-Sendfile'] = os.path.join(settings.MEDIA_ROOT, file_path.encode('utf-8'))
    response['Content-Disposition'] = 'attachment; filename="%s"' % file_name.encode('utf-8')
    response['Content-Type'] = mimetype
    return response
