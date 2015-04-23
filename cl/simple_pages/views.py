import json
import os

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count
from django.http import HttpResponseRedirect, Http404
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.template import loader
from django.views.decorators.cache import cache_page, never_cache

from cl.audio.models import Audio
from cl.custom_filters.decorators import check_honeypot
from cl.lib import magic
from cl.lib import search_utils
from cl.lib.bot_detector import is_bot
from cl.lib.sunburnt import sunburnt
from cl.search.models import Court, Opinion
from cl.search.forms import SearchForm
from cl.simple_pages.forms import ContactForm
from cl.stats import tally_stat


def about(request):
    """Loads the about page"""
    return render_to_response(
        'about.html',
        {'private': False},
        RequestContext(request)
    )


def faq(request):
    """Loads the FAQ page"""
    scraped_court_count = Court.objects.filter(
        in_use=True,
        has_opinion_scraper=True
    ).count()
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    response = conn.raw_query(
        **search_utils.build_total_count_query()).execute()
    total_opinion_count = response.result.numFound
    return contact(
        request,
        template_path='faq.html',
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

    search_form = SearchForm(request.GET)
    precedential_statuses = [field for field in
        search_form.fields.keys() if field.startswith('stat_')]

    # Build up the sourcing stats.
    counts = Opinion.objects.values('source').annotate(Count('source'))
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

    opinion_courts = Court.objects.filter(
        in_use=True,
        has_opinion_scraper=True)
    oral_argument_courts = Court.objects.filter(
        in_use=True,
        has_oral_argument_scraper=True)
    return render_to_response(
        'coverage_graph.html',
        {
            'sorted_courts': courts_json,
            'precedential_statuses': precedential_statuses,
            'count_pro': count_pro,
            'count_lawbox': count_lawbox,
            'count_scraper': count_scraper,
            'courts_with_opinion_scrapers': opinion_courts,
            'courts_with_oral_argument_scrapers': oral_argument_courts,
            'private': False
        },
        RequestContext(request))


def feeds(request):
    opinion_courts = Court.objects.filter(
        in_use=True,
        has_opinion_scraper=True
    )
    oral_argument_courts = Court.objects.filter(
        in_use=True,
        has_oral_argument_scraper=True
    )
    return render_to_response(
        'feeds.html',
        {
            'opinion_courts': opinion_courts,
            'oral_argument_courts': oral_argument_courts,
            'private': False
        },
        RequestContext(request)
    )


def contribute(request):
    return render_to_response(
        'contribute.html',
        {'private': False},
    )


@check_honeypot(field_name='skip_me_if_alive')
def contact(
        request,
        template_path='contact_form.html',
        template_data=None,
        initial=None):
    """This is a fairly run-of-the-mill contact form, except that it can be
    overridden in various ways so that its logic can be called from other
    functions.
    """
    # For why this is necessary, see
    # https://stackoverflow.com/questions/24770130/ and the related link,
    # http://effbot.org/zone/default-values.htm. Basically, you can't have a
    # mutable data type like a dict as a default argument without its state
    # being carried around from one function call to the next.
    if template_data is None:
        template_data = {}
    if initial is None:
        initial = {}

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
                'CourtListener message from "%s": %s' % (cd['name'],
                                                         cd['subject']),
                cd['message'],
                cd.get('email', 'noreply@example.com'),
                email_addresses, )
            # we must redirect after success to avoid problems with people
            # using the refresh button.
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
        'contact_thanks.html',
        {'private': True},
        RequestContext(request)
    )


def advanced_search(request):
    return render_to_response(
        'advanced_search.html',
        {'private': False},
        RequestContext(request)
    )


def old_terms(request, v):
    return render_to_response(
        'terms/%s.html' % v,
        {'title': 'Archived Terms and Policies, v%s - CourtListener.com' % v,
         'private': True},
        RequestContext(request),
    )


def latest_terms(request):
    return render_to_response(
        'terms/latest.html',
        {'private': False},
        RequestContext(request),
    )


class HttpResponseTemporaryUnavailable(HttpResponse):
    status_code = 503


@never_cache
def show_maintenance_warning(request):
    """Blocks access to a URL, and instead loads a maintenance warning.

    Uses a 503 status code, which preserves SEO. See:
    https://plus.google.com/115984868678744352358/posts/Gas8vjZ5fmB
    """
    t = loader.get_template('maintenance.html')
    return HttpResponseTemporaryUnavailable(
        t.render({'private': True}))


@cache_page(60 * 60 * 12)  # 12 hours
def robots(request):
    """Generate the robots.txt file"""
    response = HttpResponse(mimetype='text/plain')
    t = loader.get_template('robots.txt')
    response.write(t.render({}))
    return response


def validate_for_bing(request):
    return HttpResponse('<?xml version="1.0"?><users><user>8BA95D8EAA744379D80D9F70847EA156</user></users>')


def validate_for_google(request):
    return HttpResponse('google-site-verification: googleef3d845637ccb353.html')


def validate_for_google2(request):
    return HttpResponse('google-site-verification: google646349975c2495b6.html')


def validate_for_wot(request):
    return HttpResponse('bcb982d1e23b7091d5cf4e46826c8fc0')


def tools_page(request):
    return render_to_response(
        'tools.html',
        {'private': False},
        RequestContext(request)
    )


def browser_warning(request):
    return render_to_response(
        'browser_warning.html',
        {'private': True},
        RequestContext(request)
    )


def serve_static_file(request, file_path=''):
    """Sends a static file to a user.

    This serves up the static case files such as the PDFs in a way that can be
    blocked from search engines if necessary. We do four things:
     - Look up the document  or audio file associated with the filepath
     - Check if it's blocked
     - If blocked, we set the x-robots-tag HTTP header
     - Serve up the file using Apache2's xsendfile
    """
    response = HttpResponse()
    file_loc = os.path.join(settings.MEDIA_ROOT, file_path.encode('utf-8'))
    if file_path.startswith('mp3'):
        item = get_object_or_404(Audio, local_path_mp3=file_path)
        mimetype = 'audio/mpeg'
    else:
        item = get_object_or_404(Document, local_path=file_path)
        try:
            mimetype = magic.from_file(file_loc, mime=True)
        except IOError:
            raise Http404

    if item.blocked:
        response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'

    if settings.DEVELOPMENT:
        # X-Sendfile will only confuse you in a dev env.
        response.content = open(file_loc, 'r').read()
    else:
        response['X-Sendfile'] = file_loc
    file_name = file_path.split('/')[-1]
    response['Content-Disposition'] = 'attachment; filename="%s"' % \
                                      file_name.encode('utf-8')
    response['Content-Type'] = mimetype
    if not is_bot(request):
        tally_stat('case_page.static_file.served')
    return response
