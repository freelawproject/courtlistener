from reporters_db import REPORTERS


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

from django.db.models import Q
from dateutil.relativedelta import relativedelta
from cl.people_db.models import Person

def find_person(name_last, court_id, name_first=None, case_date=None, 
                require_dates=False, raise_mult=False, raise_zero=False):
    """Uniquely identifies a judge by both name and metadata. Prints a warning if couldn't find and raises an
    exception if not unique."""
    
    # don't check for dates
    if not require_dates:
        candidates = Person.objects.filter(
            name_last__iexact=name_last,        
            positions__court_id=court_id,
        )    
        if len(candidates) == 0:
            print("No judge: Last name '%s', position '%s'." % (name_last,court_id))
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
        print("No judge: Last name '%s', position '%s'." % (name_last,court_id))
        if raise_zero:
            raise Exception("No judge: Last name '%s', position '%s'." % (name_last,court_id))
        else:
             print("No judge: Last name '%s', position '%s'." % (name_last,court_id))
             return None
    
    if name_first is not None:
        candidates = Person.objects.filter(
            Q(name_last__iexact=name_last),        
            Q(name_first__iexact=name_first),
            Q(positions__court_id=court_id),
            Q(positions__date_start__lt=case_date + relativedelta(years=1)),
            Q(positions__date_termination__gt=case_date - relativedelta(years=1)) | Q( positions__date_termination=None)
        )
        if len(candidates) == 1:
            return candidates[0]
        print('First name %s not found in group %s' % (name_first, str([c.name_first for c in candidates])))

        
    if raise_mult:         
        raise Exception("Multiple judges: Last name '%s', court '%s', options: %s." % (name_last,court_id, str([c.name_first for c in candidates])))

