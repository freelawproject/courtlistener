# -*- coding: utf-8 -*-

from alert.search.models import Document
from alert.tinyurl.encode_decode import ascii_to_num
from django.contrib.sites.models import Site
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_page
import string

@cache_page(60 * 5)
def redirect_short_url(request, encoded_string):
    '''Redirect a user to the CourtListener site from the crt.li site.'''

    # strip any GET arguments from the string
    index = string.find(encoded_string, "&")
    if index != -1:
        # there's an ampersand. Strip the GET params.
        encoded_string = encoded_string[0:index]

    # Decode the string to find the object ID, and construct a link.
    num = ascii_to_num(encoded_string)

    # Get the document or throw a 404
    doc = get_object_or_404(Document, documentUUID=num)

    # Construct the URL
    slug = doc.citation.slug
    court = str(doc.court.courtUUID)
    current_site = Site.objects.get_current()
    URL = "http://www.courtlistener.com/" + court + "/" + \
        encoded_string + "/" + slug + "/"
    return HttpResponsePermanentRedirect(URL)
