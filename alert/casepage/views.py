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


def make_caption(doc):
    """Make a proper caption"""
    caption = doc.citation.case_name
    if doc.citation.neutral_cite:
        caption += ", %s" % doc.citation.neutral_cite
        return caption  # neutral cites lack the parentheses, so we're done here.
    elif doc.citation.federal_cite_one:
        caption += ", %s" % doc.citation.federal_cite_one
    elif doc.citation.specialty_cite_one:
        caption += ", %s" % doc.citation.specialty_cite_one
    elif doc.citation.state_cite_regional:
        caption += ", %s" % doc.citation.state_cite_regional
    elif doc.citation.state_cite_one:
        caption += ", %s" % doc.citation.state_cite_one
    elif doc.citation.westlaw_cite and doc.citation.lexis_cite:
        # If both WL and LEXIS
        caption += ", %s, %s" % (doc.citation.westlaw_cite, doc.citation.lexis_cite)
    elif doc.citation.westlaw_cite:
        # If only WL
        caption += ", %s" % doc.citation.westlaw_cite
    elif doc.citation.lexis_cite:
        # If only LEXIS
        caption += ", %s" % doc.citation.lexis_cite
    elif doc.citation.docket_number:
        caption += ", %s" % doc.citation.docket_number
    caption += ' ('
    if doc.court.citation_string != 'SCOTUS':
        caption += re.sub(' ', '&nbsp;', doc.court.citation_string)
        caption += '&nbsp;'
    caption += '%s)' % doc.date_filed.isoformat().split('-')[0]  # b/c strftime f's up before 1900.
    return caption


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
    caption = make_caption(doc)
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

    return render_to_response(
        'view_case.html',
        {'title': title,
         'caption': caption,
         'citation_string': citation_string,
         'doc': doc,
         'court': ct,
         'favorite_form': favorite_form,
         'get_string': get_string,
         'private': doc.blocked,
         'cited_by_trunc': cited_by_trunc},
        RequestContext(request)
    )


def view_case_citations(request, pk, casename):
    # Decode the id string back to an int
    pk = ascii_to_num(pk)

    # Look up the document, title
    doc = get_object_or_404(Document, pk=pk)
    caption = make_caption(doc)
    title = '%s, %s' % (trunc(doc.citation.case_name, 100), make_citation_string(doc))

    # Get list of citing cases, ordered by influence
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
                               'caption': caption,
                               'doc': doc,
                               'private': private,
                               'citing_cases': citing_cases},
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
