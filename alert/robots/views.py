

from alert.alertSystem.models import Document
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext, loader, Context
from django.views.decorators.cache import cache_page


@cache_page(60 * 60)
def robots(request):
    '''Generate the robots.txt file'''
    response = HttpResponse(mimetype = 'text/plain')

    docs = Document.objects.filter(blocked = True)

    # make them into pretty HTML
    t = loader.get_template('robots/robots.txt')
    c = Context({'docs': docs})
    text = t.render(c)
    response.write(text)
    return response

