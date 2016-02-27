# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from cl.search.models import Docket, Opinion, OpinionCluster, Court
from cl.people_db.models import Person, Position
from cl.citations.find_citations import  get_citations
from cl.lib.import_lib import map_citations_to_models


# used to identify dates
ARGUED_TAGS = ['argued', 'submitted', 'submitted on briefs', 'on briefs']
REARG_DENIED_TAGS = ['reargument denied', 'rehearing denied']
REARG_TAGS = ['reargued']

# used to map the parsed opinion types to their tags in the populated opinion objects
OPINION_TYPE_MAPPING = {
    'opinion': '020lead'
    ,'dissent': '040dissent'
    ,'concurrence': '030concurrence'
}


def find_person(name, court_id, case_date):
    """Uniquely identifies a judge by both name and metadata or raises and exception."""
    # EA: I think you can directly filter on name and position.
    candidates = Person.objects.filter(name_last__iexact=name)
    unique_person = None
    court = Court.objects.get(pk=court_id)
    for person in candidates:
        # give a 1-year margin of error for start and end dates
        positions = Position.objects.filter(
            person=person
            ,position_type='judge'
            ,court=court
            ,date_start__leq = case_date.year - relativedelta(years=1)
            ,date_termination__geq = case_date.year + relativedelta(years=1)
        )
        if positions:
            if unique_person:
                raise Exception("Found multiple judges with last name '%s' and matching positions." % name)
            unique_person = person
    if not unique_person:
        #raise Exception("Failed to find a judge with last name '%s` and matching position." % name)
        print("Failed to find a judge with last name '%s` and matching position." % name)        
    return unique_person



def make_and_save(item):
    """Associates case data from `parse_opinions` with objects. Saves these objects."""
    if not item:
        return []

    # find relevent dates
    argued_date = reargued_date = reargue_denied_date = opinion_date = None
    for type in item['dates']:
        for date_info in type:
            # check for untagged dates that will be assigned to opinion_date
            if len(date_info) == 1:
                opinion_date = date_info[0]
                continue
            # try to figure out what type of date it is based on its tag string
            if date_info[0] in ARGUED_TAGS:
                argued_date = date_info[1]
            elif date_info[0] in REARG_TAGS:
                reargued_date = date_info[1]
            elif date_info[0] in REARG_DENIED_TAGS:
                reargue_denied_date = date_info[1]
            # EA: basestring is python 2 only, could we do this in a way that is 2/3 compatible
            elif isinstance(date_info[0], basestring) and 'cert' in date_info[0]:
                # we don't have an item for cert acceptance/denial
                pass
            else:                
                opinion_date = date_info[1]

    docket = Docket(
        date_argued=argued_date
        ,date_reargued=reargued_date
        ,date_reargument_denied=reargue_denied_date
        ,court_id=item['court_id']
        ,case_name_short=item['case_name_short']
        ,case_name=item['case_name']
        ,case_name_full=item['case_name_full']
        ,docket_number=item['docket']
    )
    docket.save()

    panel = [find_person(n, item['court_id'], argued_date or opinion_date) for n in item['panel']]
    panel = [x for x in panel if x is not None]
    # get citations in the form of, e.g. {'federal_cite_one': '1 U.S. 1', ...}
    all_citations = map_citations_to_models([get_citations(c)[0] for c in item['citations']])

    cluster = OpinionCluster(
        docket=docket
        ,precedential_status=('Unpublished' if item['unpublished'] else 'Published')
        ,date_filed=opinion_date
        ,panel=panel
        ,case_name_short=item['case_name_short']
        ,case_name=item['case_name']
        ,case_name_full=item['case_name_full']
        ,source='Z'
        ,attorneys=item['attorneys']
        ,posture=item['posture']
        ,**all_citations
    )
    cluster.save()

    for opinion_info in item['opinions']:
        if opinion_info['byline'] is None:
            author = None
        else:
            author = find_person(opinion_info['byline'], item['court_id'], opinion_date or argued_date)
        joined_by = [find_person(n, item['court_id'], opinion_date or argued_date) for n in opinion_info['joining']]
        opinion = Opinion(
            cluster=cluster
            ,author=author
            ,joined_by=joined_by
            ,type=OPINION_TYPE_MAPPING[opinion_info['type']]
            ,html_columbia=opinion_info['opinion']
        )
        opinion.save()

if __name__ == '__main__':
    from cl.corpus_importer.import_columbia.parse_opinions import parse_file
    parsed = parse_file('cl/corpus_importer/import_columbia/test_opinions/0b59c80d9043a003.xml')
    make_and_save(parsed)
