# coding=utf-8
import json
import logging
import os
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404
from django.template import loader
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from rest_framework.status import HTTP_429_TOO_MANY_REQUESTS

from cl.audio.models import Audio
from cl.custom_filters.decorators import check_honeypot
from cl.lib import magic
from cl.lib.decorators import track_in_piwik
from cl.opinion_page.views import make_rd_title
from cl.people_db.models import Person
from cl.people_db.tasks import make_thumb_if_needed
from cl.search.forms import SearchForm
from cl.search.models import Court, OpinionCluster, Opinion, RECAPDocument, \
    Docket
from cl.simple_pages.forms import ContactForm

logger = logging.getLogger(__name__)


def about(request):
    """Loads the about page"""
    return render(request, 'about.html', {'private': False})


def faq(request):
    """Loads the FAQ page"""
    faq_cache_key = 'faq-stats'
    template_data = cache.get(faq_cache_key)
    if template_data is None:
        template_data = {
            'scraped_court_count': Court.objects.filter(
                in_use=True,
                has_opinion_scraper=True
            ).count(),
            'total_opinion_count': OpinionCluster.objects.all().count(),
            'total_recap_count': RECAPDocument.objects.filter(
                is_available=True).count(),
            'total_oa_minutes': (Audio.objects.aggregate(
                Sum('duration')
            )['duration__sum'] or 0) / 60,
            'total_judge_count': Person.objects.all().count(),
        }
        five_days = 60 * 60 * 24 * 5
        cache.set(faq_cache_key, template_data, five_days)

    return contact(
        request,
        template_path='faq.html',
        template_data=template_data,
        initial={'subject': 'FAQs'},
    )


def alert_help(request):
    no_feeds = Court.objects.filter(
        jurisdiction__in=[
            Court.FEDERAL_BANKRUPTCY,
            Court.FEDERAL_DISTRICT,
        ],
        pacer_has_rss_feed=False,
    )
    cache_key = 'alert-help-stats'
    data = cache.get(cache_key)
    if data is None:
        data = {
            'd_update_count': Docket.objects.filter(
                date_modified__gte=now() - timedelta(days=1)).count(),
            'de_update_count': RECAPDocument.objects.filter(
                date_modified__gte=now() - timedelta(days=1)).count(),
        }
        one_day = 60 * 60 * 24
        cache.set(cache_key, data, one_day)
    context = {
        'no_feeds': no_feeds,
        'private': False,
    }
    context.update(data)
    return render(request, 'help/alert_help.html', context)


def donation_help(request):
    return render(request, 'help/donation_help.html', {'private': False})


def markdown_help(request):
    return render(request, 'help/markdown_help.html', {'private': False})


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
    coverage_cache_key = 'coverage-data-v2'
    coverage_data = cache.get(coverage_cache_key)
    if coverage_data is None:
        courts = Court.objects.filter(in_use=True)
        courts_json = json.dumps(build_court_dicts(courts))

        search_form = SearchForm(request.GET)
        precedential_statuses = [field for field in
            search_form.fields.keys() if field.startswith('stat_')]

        # Build up the sourcing stats.
        counts = OpinionCluster.objects.values('source').annotate(Count('source'))
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

        oa_duration = Audio.objects.aggregate(
            Sum('duration'))['duration__sum']
        if oa_duration:
            oa_duration /= 60  # Avoids a "unsupported operand type" error

        coverage_data = {
            'sorted_courts': courts_json,
            'precedential_statuses': precedential_statuses,
            'oa_duration': oa_duration,
            'count_pro': count_pro,
            'count_lawbox': count_lawbox,
            'count_scraper': count_scraper,
            'courts_with_opinion_scrapers': opinion_courts,
            'courts_with_oral_argument_scrapers': oral_argument_courts,
            'private': False
        }
        one_day = 60 * 60 * 24
        cache.set(coverage_cache_key, coverage_data, one_day)

    return render(request, 'coverage.html', coverage_data)


def feeds(request):
    return render(request, 'feeds.html', {
        'opinion_courts': Court.objects.filter(in_use=True,
                                               has_opinion_scraper=True),
        'private': False
    })


def podcasts(request):
    return render(request, 'podcasts.html', {
        'oral_argument_courts': Court.objects.filter(
            in_use=True,
            has_oral_argument_scraper=True,
        ),
        'count': Audio.objects.all().count(),
        'private': False
    })


def contribute(request):
    return render(request, 'contribute.html', {'private': False})


@check_honeypot(field_name='skip_me_if_alive')
def contact(
        request,
        template_path='contact_form.html',
        template_data=None,
        initial=None):
    """This is a fairly run-of-the-mill contact form, except that it can be
    overridden in various ways so that its logic can be called from other
    functions.

    We also use a field called phone_number in place of the subject field to
    defeat spam.
    """
    if template_data is None:
        template_data = {}
    if initial is None:
        initial = {}

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # Uses phone_number as Subject field to defeat spam. If this field
            # begins with three digits, assume it's spam; fake success.
            if re.match('\d{3}', cd['phone_number']):
                logger.info("Detected spam message. Not sending email.")
                return HttpResponseRedirect(reverse(u'contact_thanks'))

            default_from = settings.DEFAULT_FROM_EMAIL
            EmailMessage(
                subject=u'[CourtListener] Contact: '
                        u'{phone_number}'.format(**cd),
                body=u'Subject: {phone_number}\n'
                     u'From: {name} ({email})\n'
                     u'\n\n{message}\n\n'
                     u'Browser: {browser}'.format(
                         browser=request.META.get(u'HTTP_USER_AGENT', u"Unknown"),
                         **cd
                     ),
                to=['info@free.law'],
                reply_to=[cd.get(u'email', default_from) or default_from],
            ).send()
            return HttpResponseRedirect(reverse(u'contact_thanks'))
    else:
        # the form is loading for the first time
        try:
            initial[u'email'] = request.user.email
            initial[u'name'] = request.user.get_full_name()
            form = ContactForm(initial=initial)
        except AttributeError:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm(initial=initial)

    template_data.update(
        {u'form': form,
         u'private': False}
    )
    return render(request, template_path, template_data)


def contact_thanks(request):
    return render(request, u'contact_thanks.html', {u'private': True})


def advanced_search(request):
    return render(request, 'advanced_search.html', {'private': False})


def old_terms(request, v):
    return render(request, 'terms/%s.html' % v, {
        'title': u'Archived Terms of Service and Policies, v%s – CourtListener.com' % v,
        'private': True
    })


def latest_terms(request):
    return render(request, 'terms/latest.html', {
        'title': u'Terms of Service and Policies – CourtListener.com',
        'private': False
    })


@cache_page(60 * 60 * 12)  # 12 hours
def robots(request):
    """Generate the robots.txt file"""
    response = HttpResponse(content_type='text/plain')
    t = loader.get_template('robots.txt')
    response.write(t.render({}))
    return response


@cache_page(60 * 60 * 12)  # 12 hours
def humans(request):
    """Generate the humans.txt file"""
    response = HttpResponse(content_type='text/plain')
    t = loader.get_template('humans.txt')
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
    return render(request, 'tools.html', {'private': False})


def browser_warning(request):
    return render(request, 'browser_warning.html', {'private': True})


def ratelimited(request, exception):
    return render(request, '429.html', {'private': True},
                  status=HTTP_429_TOO_MANY_REQUESTS)


@track_in_piwik
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
    elif file_path.startswith('recap'):
        # Either we serve up a special HTML file to make twitter happy, or we
        # serve the PDF to make a human happy.
        is_twitterbot = request.META.get('HTTP_USER_AGENT').startswith(
            "Twitterbot")
        og_disabled = bool(request.GET.get('no-og'))
        # xxx - nuke post debugging!!!
        is_twitterbot = True
        if is_twitterbot and not og_disabled:
            # Create an HTML page that wraps the PDF and serve
            # that up so Twitter can make a nice card.
            try:
                rd = RECAPDocument.objects.get(filepath_local=file_path)
            except (RECAPDocument.DoesNotExist,
                    RECAPDocument.MultipleObjectsReturned):
                pass
            else:
                make_thumb_if_needed(rd)
                return render(request, 'recap_document_twitter.html', {
                    'title': make_rd_title(rd),
                    'document': rd,
                    'private': True,
                })
        # A human or unable to find the item in the DB. Create an empty object,
        # and set it to blocked. (All recap pdfs are blocked.)
        item = RECAPDocument()
        item.blocked = True
        mimetype = 'application/pdf'
    else:
        item = get_object_or_404(Opinion, local_path=file_path)
        item.blocked = item.cluster.blocked
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
    response['Content-Disposition'] = 'inline; filename="%s"' % \
                                      file_name.encode('utf-8')
    response['Content-Type'] = mimetype
    return response
