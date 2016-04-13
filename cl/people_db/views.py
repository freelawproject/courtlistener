from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext

from cl.people_db.models import Person


def view_person(request, pk, slug):
    person = get_object_or_404(Person, pk=pk)

    # Redirect the user if they're trying to check out an alias.
    if person.is_alias:
        return HttpResponseRedirect(reverse('view_person', args=[
            person.is_alias_of.pk, person.is_alias_of.slug
        ]))

    # Make the title string.
    locations = ', '.join(
        [p.court.short_name for p in person.positions.all() if p.court]
    )
    title = person.name_full
    if locations:
        title += " (%s)" % locations

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

    return render_to_response(
        'view_person.html',
        {'person': person,
         'title': title,
         'aba_ratings': person.aba_ratings.all().order_by('-date_rated'),
         'political_affiliations': (person.political_affiliations.all()
                                    .order_by('-date_start')),
         'positions': positions,
         'educations': person.educations.all().order_by('-degree_year'),
         'private': False},
        RequestContext(request),
    )
