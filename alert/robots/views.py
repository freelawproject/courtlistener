from django.http import HttpResponse
from django.template import loader, Context
from django.views.decorators.cache import cache_page


@cache_page(60 * 60)
def robots(request):
    """Generate the robots.txt file"""
    response = HttpResponse(mimetype='text/plain')
    t = loader.get_template('robots/robots.txt')
    c = Context({})
    response.write(t.render(c))
    return response

