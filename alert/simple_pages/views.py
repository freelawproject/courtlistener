import json

from django.db.models import Count
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.template import loader, Context
from django.views.decorators.cache import cache_page, never_cache
from alert.lib import search_utils
from alert.lib.sunburnt import sunburnt

from alert.search.models import Court, Document
from alert import settings
from alert.simple_pages.forms import ContactForm
from alert.custom_filters.decorators import check_honeypot


def about(request):
    """Loads the about page"""
    return render_to_response(
        'simple_pages/about.html',
        {'private': False},
        RequestContext(request)
    )


def faq(request):
    """Loads the FAQ page"""
    scraped_court_count = Court.objects.filter(in_use=True, has_scraper=True).count()
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    response = conn.raw_query(
        **search_utils.build_total_count_query()).execute()
    total_opinion_count = response.result.numFound
    return contact(
        request,
        template_path='simple_pages/faq.html',
        template_data={
            'scraped_court_count': scraped_court_count,
            'total_opinion_count': total_opinion_count,
        },
        initial={'subject': 'FAQs'},
    )


def build_court_dicts(courts):
    """Takes the court objects, and manipulates them into a list of more useful
    dictionaries"""
    court_dicts = [{'pk': 'all',
                    'short_name': u'All Courts'}]
    court_dicts.extend([{'pk': court.pk,
                         'short_name': court.full_name, }
                         #'notes': court.notes}
                        for court in courts])
    return court_dicts


def coverage_graph(request):
    courts = Court.objects.filter(in_use=True)
    courts_json = json.dumps(build_court_dicts(courts))

    # Build up the sourcing stats.
    counts = Document.objects.values('source').annotate(Count('source'))
    count_pro = 0
    count_lawbox = 0
    count_scraper = 0
    for d in counts:
        if 'R' in d['source']:
            count_pro += d['source__count']
        if 'C' in d['source']:
            count_scraper += d['source__count']
        if 'L' in d['source']:
            count_lawbox += d['source__count']

    courts_with_scrapers = Court.objects.filter(in_use=True, has_scraper=True)
    return render_to_response('simple_pages/coverage_graph.html',
                              {'sorted_courts': courts_json,
                               'count_pro': count_pro,
                               'count_lawbox': count_lawbox,
                               'count_scraper': count_scraper,
                               'courts_with_scrapers': courts_with_scrapers,
                               'private': False},
                              RequestContext(request))


@check_honeypot(field_name='skip_me_if_alive')
def contact(
        request,
        template_path='simple_pages/contact_form.html',
        template_data={},
        initial={}):
    """This is a fairly run-of-the-mill contact form, except that it can be overridden in various ways so that its
    logic can be called from other functions.
    """

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # pull the email addresses out of the MANAGERS tuple
            i = 0
            email_addresses = []
            while i < len(settings.MANAGERS):
                email_addresses.append(settings.MANAGERS[i][1])
                i += 1

            # send the email to the MANAGERS
            send_mail(
                'CourtListener message from "%s": %s' % (cd['name'], cd['subject']),
                cd['message'],
                cd.get('email', 'noreply@example.com'),
                email_addresses, )
            # we must redirect after success to avoid problems with people using the refresh button.
            return HttpResponseRedirect('/contact/thanks/')
    else:
        # the form is loading for the first time
        try:
            initial['email'] = request.user.email
            initial['name'] = request.user.get_full_name()
            form = ContactForm(initial=initial)
        except AttributeError:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm(initial=initial)

    template_data.update(
        {'form': form,
         'private': False}
    )
    return render_to_response(
        template_path,
        template_data,
        RequestContext(request)
    )


def contact_thanks(request):
    return render_to_response(
        'simple_pages/contact_thanks.html',
        {'private': True},
        RequestContext(request)
    )


def advanced_search(request):
    return render_to_response(
        'simple_pages/advanced_search.html',
        {'private': False},
        RequestContext(request)
    )


class HttpResponseTemporaryUnavailable(HttpResponse):
    status_code = 503

@never_cache
def show_maintenance_warning(request):
    """Blocks access to a URL, and instead loads a maintenance warning.

    Uses a 503 status code, which preserves SEO. See:
    https://plus.google.com/115984868678744352358/posts/Gas8vjZ5fmB
    """
    t = loader.get_template('simple_pages/maintenance.html')
    return HttpResponseTemporaryUnavailable(t.render(Context({'private': True})))


@cache_page(60 * 60)
def robots(request):
    """Generate the robots.txt file"""
    response = HttpResponse(mimetype='text/plain')
    t = loader.get_template('simple_pages/robots.txt')
    c = Context({})
    response.write(t.render(c))
    return response


def validate_for_bing(request):
    return HttpResponse('<?xml version="1.0"?><users><user>8BA95D8EAA744379D80D9F70847EA156</user></users>')


def validate_for_google(request):
    return HttpResponse('google-site-verification: googleef3d845637ccb353.html')


def validate_for_google2(request):
    return HttpResponse('google-site-verification: google646349975c2495b6.html')


def validate_for_wot(request):
    return HttpResponse('bcb982d1e23b7091d5cf4e46826c8fc0')
