# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from cl.search.models import Docket, Opinion, OpinionCluster
from cl.people_db.models import Person
from cl.citations.find_citations import get_citations
from cl.lib.import_lib import map_citations_to_models


# used to identify dates
ARGUED_TAGS = ['argued', 'submitted', 'submitted on briefs', 'on briefs']
REARGUE_DENIED_TAGS = ['reargument denied', 'rehearing denied']
REARGUE_TAGS = ['reargued']
CERT_GRANTED_TAGS = ['certiorari granted']
CERT_DENIED_TAGS = ['certiorari denied']

# used to map the parsed opinion types to their tags in the populated opinion objects
OPINION_TYPE_MAPPING = {
    'opinion': '020lead'
    ,'dissent': '040dissent'
    ,'concurrence': '030concurrence'
}


def find_person(name, court_id, case_date):
    """Uniquely identifies a judge by both name and metadata or raises and exception."""
    # EA: I think you can directly filter on name and position.
    candidates = Person.objects.filter(
        name_last__iexact=name,
        positions__position_type='judge',
        positions__court_id=court_id,
        positions__date_start__leq=case_date.year + relativedelta(years=1),
        positions__date_termination__geq=case_date.year - relativedelta(years=1),
    )
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        raise Exception("Found multiple judges with last name '%s' and matching positions." % name)
    else:
        print("Failed to find a judge with last name '%s` and matching position." % name) 
        return None


def make_and_save(item):
    """Associates case data from `parse_opinions` with objects. Saves these objects."""
    date_filed = date_argued = date_reargued = date_reargument_denied = date_cert_granted = date_cert_denied = None
    for date_cluster in item['dates']:
        for date_info in date_cluster:
            # check for any dates that clearly aren't dates
            if date_info[1].year < 1800 or date_info[1].year > 2020:
                continue
            # check for untagged dates that will be assigned to date_filed
            if not date_info[0]:
                date_filed = date_info[0]
                continue
            # try to figure out what type of date it is based on its tag string
            if date_info[0] in ARGUED_TAGS:
                date_argued = date_info[1]
            elif date_info[0] in REARGUE_TAGS:
                date_reargued = date_info[1]
            elif date_info[0] in REARGUE_DENIED_TAGS:
                date_reargument_denied = date_info[1]
            elif date_info[0] in CERT_GRANTED_TAGS:
                date_cert_granted = date_info[1]
            elif date_info[0] in CERT_DENIED_TAGS:
                date_cert_denied = date_info[1]
            else:
                print "Found unknown date tag '%s' with date '%s'." % date_info

    docket = Docket(
        date_argued=date_argued
        ,date_reargued=date_reargued
        ,date_cert_granted=date_cert_granted
        ,date_cert_denied=date_cert_denied
        ,date_reargument_denied=date_reargument_denied
        ,court_id=item['court_id']
        ,case_name_short=item['case_name_short']
        ,case_name=item['case_name']
        ,case_name_full=item['case_name_full']
        ,docket_number=item['docket']
    )
    docket.save()

    panel = [find_person(n, item['court_id'], date_argued or date_filed) for n in item['panel']]
    panel = [x for x in panel if x is not None]
    # get citations in the form of, e.g. {'federal_cite_one': '1 U.S. 1', ...}
    all_citations = map_citations_to_models([get_citations(c)[0] for c in item['citations']])

    cluster = OpinionCluster(
        docket=docket
        ,precedential_status=('Unpublished' if item['unpublished'] else 'Published')
        ,date_filed=date_filed
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
            author = find_person(opinion_info['byline'], item['court_id'], date_filed or date_argued)
        joined_by = [find_person(n, item['court_id'], date_filed or date_argued) for n in opinion_info['joining']]
        joined_by = [x for x in joined_by if x is not None]
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
