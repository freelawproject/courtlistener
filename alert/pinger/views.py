from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext

from django.conf import settings
from django.core.urlresolvers import reverse


def validate_for_bing(request):
    return HttpResponse('<?xml version="1.0"?><users><user>3251009A11EF3EB9D6A7B40EAD9264AD</user></users>')


def validate_for_bing2(request):
    return HttpResponse('<?xml version="1.0"?><users><user>8BA95D8EAA744379D80D9F70847EA156</user></users>')


def validate_for_google(request):
    return HttpResponse('google-site-verification: googleef3d845637ccb353.html')


def validate_for_google2(request):
    return HttpResponse('google-site-verification: google646349975c2495b6.html')
