import json

from django.db.models import Count
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.template import loader, Context
from django.views.decorators.cache import cache_page

from alert.search.models import Court, Document
from alert import settings
from alert.simple_pages.forms import ContactForm
from alert.honeypot.decorators import check_honeypot


def about(request):
    """Loads the about page"""
    return render_to_response(
        'simple_pages/about.html',
        {'private': False},
        RequestContext(request)
    )


def faq(request):
    """Loads the FAQ page"""
    return contact(
        request,
        template_path='simple_pages/faqs.html',
        initial={'subject': 'FAQs'}
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
def contact(request, template_path='simple_pages/contact_form.html', initial={}):
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

    return render_to_response(
        template_path,
        {'form': form,
         'private': False},
        RequestContext(request)
    )


def contact_thanks(request):
    return render_to_response('simple_pages/contact_thanks.html',
                              {'private': False},
                              RequestContext(request))


@cache_page(60 * 60)
def robots(request):
    """Generate the robots.txt file"""
    response = HttpResponse(mimetype='text/plain')
    t = loader.get_template('simple_pages/robots.txt')
    c = Context({})
    response.write(t.render(c))
    return response
