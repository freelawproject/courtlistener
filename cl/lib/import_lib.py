from dateutil.relativedelta import relativedelta
from django.db.models import Min, Q
from reporters_db import REPORTERS

from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.people_db.models import Person
from cl.search.models import Court, Opinion


def map_citations_to_models(citations):
    """Takes a list of citations and converts it to a dict mapping those
    citations to the model itself.

    For example, an opinion mentioning 1 U.S. 1 and 1 F.2d 1 (impossible, I
    know) would get mapped to:

    {
     'federal_cite_one': '1 U.S. 1',
     'federal_cite_two': '1 F.2d 1',
    }
    """
    def add_mapping(mapping, key, value):
        """Add the mapping to federal_cite_one, if it doesn't have a value.
        Else, add to federal_cite_two. Etc.
        """
        punt_count = 0
        numbers = ['one', 'two', 'three']
        for number in numbers:
            try:
                _ = mapping['%s_cite_%s' % (key, number)]
                # That key is used. Try the next one...
                punt_count += 1
                if punt_count == len(numbers):
                    raise("Failed to add citation to the mapping dict (it "
                          "was full!): %s" % value)
                continue
            except KeyError:
                # Key not found, so add the value and break.
                mapping['%s_cite_%s' % (key, number)] = value
                break
        return mapping

    cite_mapping = {}
    for citation in citations:
        cite_type = (REPORTERS[citation.canonical_reporter]
                     [citation.lookup_index]
                     ['cite_type'])
        if cite_type in ['federal', 'state', 'specialty']:
            cite_mapping = add_mapping(cite_mapping, cite_type,
                                       citation.base_citation())
        elif cite_type == 'state_regional':
            cite_mapping['state_cite_regional'] = citation.base_citation()
        elif cite_type == 'scotus_early':
            cite_mapping['scotus_early_cite'] = citation.base_citation()
        elif cite_type == 'specialty_lexis':
            cite_mapping['lexis_cite'] = citation.base_citation()
        elif cite_type == 'specialty_west':
            cite_mapping['westlaw_cite'] = citation.base_citation()
        elif cite_type == 'neutral':
            cite_mapping['neutral_cite'] = citation.base_citation()

    return cite_mapping


def find_person(name_last, court_id, name_first=None, case_date=None,
                require_dates=False, raise_mult=False, raise_zero=False):
    """Uniquely identifies a judge by both name and metadata. Prints a warning
    if couldn't find and raises an exception if not unique.
    """

    # don't check for dates
    if not require_dates:
        candidates = Person.objects.filter(
            name_last__iexact=name_last,
            positions__court_id=court_id,
        )
        if len(candidates) == 0:
            print("No judge: Last name '%s', position '%s'." % (
                name_last.encode('utf-8'),
                court_id
            ))
            return None
        if len(candidates) == 1:
            return candidates[0]

    if case_date is None:
        raise Exception("No case date provided.")

    # check based on dates
    candidates = Person.objects.filter(
        Q(name_last__iexact=name_last),
        Q(positions__court_id=court_id),
        Q(positions__date_start__lt=case_date + relativedelta(years=1)),
        Q(positions__date_termination__gt=case_date - relativedelta(years=1)) | Q(positions__date_termination=None)
    )
    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) == 0:
        msg = "No judge: Last name '%s', position '%s'." % (name_last, court_id)
        print(msg)
        if raise_zero:
            raise Exception(msg)
        else:
            return None

    if name_first is not None:
        candidates = Person.objects.filter(
            Q(name_last__iexact=name_last),
            Q(name_first__iexact=name_first),
            Q(positions__court_id=court_id),
            Q(positions__date_start__lt=case_date + relativedelta(years=1)),
            Q(positions__date_termination__gt=case_date - relativedelta(years=1)) |
            Q(positions__date_termination=None),
        )
        if len(candidates) == 1:
            return candidates[0]
        print('First name %s not found in group %s' % (name_first, str([c.name_first for c in candidates])))

    if raise_mult:
        raise Exception(
            "Multiple judges: Last name '%s', court '%s', options: %s." %
            (name_last, court_id, str([c.name_first for c in candidates]))
        )


def get_candidate_judges(judge_str, court_id, event_date):
    """Figure out who a judge is from a string and some metadata.

    :param judge_str: A string containing the judge's name.
    :param court_id: A CL Court ID where the case occurred.
    :param event_date: The date of the case.
    :return: Tuple consisting of (Judge, judge_str), where Judge is a judge
    object or None if a judge cannot be identified, and s is the original
    string passed in.
    """
    if not judge_str:
        return None

    judges = find_judge_names(judge_str)

    if len(judges) == 0:
        return []

    candidates = []
    for judge in judges:
        candidates.append(find_person(judge, court_id, case_date=event_date))
    return [c for c in candidates if c is not None]


def get_scotus_judges(d):
    """Get the panel of scotus judges at a given date."""
    return Person.objects.filter(                 # Find all the judges...
        Q(positions__court_id='scotus'),          # In SCOTUS...
        Q(positions__date_start__lt=d),           # Started as of the date...
        Q(positions__date_retirement__gt=d) |
            Q(positions__date_retirement=None),   # Haven't retired yet...
        Q(positions__date_termination__gt=d) |
            Q(positions__date_termination=None),  # Nor been terminated...
        Q(date_dod__gt=d) | Q(date_dod=None),     # And are still alive.
    ).distinct()


def get_min_dates():
    """returns a dictionary with key-value (courtid, minimum date)"""
    min_dates = {}
    courts = (Court.objects
              .exclude(dockets__clusters__source__contains="Z")
              .annotate(earliest_date=Min('dockets__clusters__date_filed')))
    for court in courts:
        min_dates[court.pk] = court.earliest_date
    return min_dates


def get_path_list():
    """Returns a set of all the local_path values so we can avoid them in
    later imports.

    This way, when we run a second, third, fourth import, we can be sure not
    to import a previous item.
    """
    return set((Opinion.objects
                .exclude(local_path='')
                .values_list('local_path', flat=True)))

def get_courtdates():
    """returns a dictionary with key-value (courtid, founding date)"""
    start_dates = {}
    courts = Court.objects
    for court in courts:
        start_dates[court.pk] = court.start_date
    return start_dates


def get_min_nocite():
    """Return a dictionary indicating the earliest case with no citations for
    every court.

    {'ala': Some-date, ...}
    """
    min_dates = {}
    courts = (Court.objects
              .filter(dockets__clusters__federal_cite_one="",
                      dockets__clusters__federal_cite_two="",
                      dockets__clusters__federal_cite_three="",
                      dockets__clusters__state_cite_one="",
                      dockets__clusters__state_cite_two="",
                      dockets__clusters__state_cite_three="",
                      dockets__clusters__state_cite_regional="",
                      dockets__clusters__specialty_cite_one="",
                      dockets__clusters__scotus_early_cite="",
                      dockets__clusters__lexis_cite="",
                      dockets__clusters__westlaw_cite="",
                      dockets__clusters__neutral_cite="")
              .annotate(earliest_date=Min('dockets__clusters__date_filed')))
    for court in courts:
        min_dates[court.pk] = court.earliest_date
    return min_dates
