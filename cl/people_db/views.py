import os
from django.conf import settings
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from cl.custom_filters.templatetags.extras import granular_date
from cl.lib import magic
from cl.lib.bot_detector import is_bot
from cl.lib.sunburnt import SolrInterface
from cl.people_db.models import Person, FinancialDisclosure
from cl.stats.utils import tally_stat


def make_title_str(person):
    """Make a nice title for somebody."""
    locations = ', '.join(
        {p.court.short_name for p in person.positions.all() if p.court}
    )
    title = person.name_full
    if locations:
        title = "%s (%s)" % (title, locations)
    return title


def make_img_path(person):
    """Make the path for a person's img tag."""

    img_path = None
    if person.has_photo:
        p = slugify(('%s-%s' % (person.name_last, person.name_first)).lower())
        if person.date_dob:
            static('judge_pics/%s-%s.jpeg'
                   % (p, granular_date(person, 'date_dob', iso=True, default='')))
        else:
            static('judge_pics/%s.jpeg' % p)

    return img_path


def view_person(request, pk, slug):
    person = get_object_or_404(Person, pk=pk)

    # Redirect the user if they're trying to check out an alias.
    if person.is_alias:
        return HttpResponseRedirect(reverse('view_person', args=[
            person.is_alias_of.pk, person.is_alias_of.slug
        ]))

    # Make the title string.
    title = "Judge %s" % make_title_str(person)

    img_path = make_img_path(person)

    # Regroup the positions by whether they're judgeships or other. This allows
    # us to use the {% ifchanged %} template tags to have two groups in the
    # template.
    judicial_positions = []
    other_positions = []
    for p in person.positions.all().order_by('-date_start'):
        if p.is_judicial_position:
            judicial_positions.append(p)
        else:
            other_positions.append(p)
    positions = judicial_positions + other_positions

    # Use Solr to get relevant opinions that the person wrote
    conn = SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    q = {
        'q': 'author_id:{p} OR panel_ids:{p}'.format(p=person.pk),
        'fl': ['id', 'court_id', 'caseName', 'absolute_url', 'court',
               'court_citation_string', 'dateFiled', 'docketNumber',
               'citeCount', 'status', 'citation'],
        'rows': 5,
        'start': 0,
        'sort': 'score desc',
        'caller': 'view_person',
    }
    authored_opinions = conn.raw_query(**q).execute()

    # Use Solr to get the oral arguments for the judge
    conn = SolrInterface(settings.SOLR_AUDIO_URL, mode='r')
    q = {
        'q': 'panel_ids:{p}'.format(p=person.pk),
        'fl': ['id', 'absolute_url', 'caseName', 'court_id', 'dateArgued',
               'docketNumber', 'court_citation_string'],
        'rows': 5,
        'start': 0,
        'sort': 'dateArgued desc',
        'caller': 'view_person',
    }
    oral_arguments_heard = conn.raw_query(**q).execute()

    return render(request, 'view_person.html', {
        'person': person,
        'title': title,
        'img_path': img_path,
        'aba_ratings': person.aba_ratings.all().order_by('-year_rated'),
        'political_affiliations': (person.political_affiliations.all()
                                   .order_by('-date_start')),
        'positions': positions,
        'educations': person.educations.all().order_by('-degree_year'),
        'authored_opinions': authored_opinions,
        'oral_arguments_heard': oral_arguments_heard,
        'ftm_last_updated': settings.FTM_LAST_UPDATED,
        'private': False
    })


def financial_disclosures_home(request):
    """The home page for financial disclosures

    This page shows:
     - A brief introduction to financial disclosure reports
     - A list of all the people we have reports for
     - A simple JS filter to find specific judges
    """
    people_with_disclosures = Person.objects.filter(
        financial_disclosures__isnull=False,
    ).distinct()
    disclosure_count = FinancialDisclosure.objects.all().count()
    people_count = people_with_disclosures.count()
    return render(request, 'financial_disclosures_home.html', {
        'people': people_with_disclosures,
        'disclosure_count': disclosure_count,
        'people_count': people_count,
        'private': False,
    })


def financial_disclosures_for_somebody(request, pk, slug):
    """Show the financial disclosures for a particular person"""
    person = get_object_or_404(Person, pk=pk)
    title = make_title_str(person)
    return render(request, 'financial_disclosures_for_somebody.html', {
        'person': person,
        'title': title,
        'private': False,
    })


def financial_disclosures_fileserver(request, pk, slug, filepath):
    """Serve up the financial disclosure files."""
    response = HttpResponse()
    file_loc = os.path.join(settings.MEDIA_ROOT, filepath.encode('utf-8'))
    if settings.DEVELOPMENT:
        # X-Sendfile will only confuse you in a dev env.
        response.content = open(file_loc, 'r').read()
    else:
        response['X-Sendfile'] = file_loc
    filename = filepath.split('/')[-1]
    response['Content-Disposition'] = 'inline; filename="%s"' % \
                                      filename.encode('utf-8')
    response['Content-Type'] = magic.from_file(file_loc, mime=True)
    if not is_bot(request):
        tally_stat('financial_reports.static_file.served')
    return response



