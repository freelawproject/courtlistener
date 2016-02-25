# -*- coding: utf-8 -*-

from django.utils.timezone import now

from cl.search.models import Docket, Opinion, OpinionCluster, Court
from cl.judges.models import Judge
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


def find_judge(name, court_id, case_date):
    """Identifies a judge by name and metadata."""
    pass
    # TODO: actually find a judge once the database has been populated with them
    # judges = Judge.objects.filter(name_last=name)
    # court = Court.objects.get(pk=court_id)


def make_and_save(item):
    """Takes the case data <item> and associates it with objects. Saves these objects."""
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
            elif isinstance(date_info[0], basestring) and 'cert' in date_info[0]:
                # we don't have an item for cert acceptance/denial
                pass
            else:                
                opinion_date = date_info[1]

    # saves docket object
    docket = Docket(
        date_created=now(),
        date_modified=now(),
        date_argued=argued_date,
        date_reargued=reargued_date,
        date_reargument_denied=reargue_denied_date,
        court_id=item.get('court_id'),
        case_name_short=item.get('case_name_short'),
        case_name=item.get('case_name'),
        case_name_full=item.get('case_name_full'),
        docket_number=item.get('docket')
    )
    docket.save()

    # grab citations in, e.g. the {'federal_cite_one': '1 U.S. 1', ...} form
    # will be passed as kwargs
    all_citations = map_citations_to_models([get_citations(c)[0] for c in item['citations']])

    # saves opinion cluster object
    cluster = OpinionCluster(
        docket=docket,
        precedential_status=('Unpublished' if item['unpublished'] else 'Published'),
        date_created=now(),
        date_modified=now(),
        date_filed=opinion_date, 
        # panel=item.get('panel', []),
        case_name_short=item.get('case_name_short'),
        case_name=item.get('case_name'),
        case_name_full=item.get('case_name_full'),
        source='Z',
        attorneys=item.get('attorneys'),
        posture=item.get('posture'),
        **all_citations
    )
    cluster.save()

    # save opinion objects
    for opinion_info in item['opinions']:
        # author = find_judge(
        #     opinion_info['byline'],
        #     item.get('court_id'),
        #     opinion_date or reargued_date
        # )
        opinion = Opinion(
            cluster=cluster,
            # author=author,
            # joined_by=
            date_created=now(),
            date_modified=now(),
            type=OPINION_TYPE_MAPPING[opinion_info['type']],
            html_columbia=opinion_info['opinion']
        )
        opinion.save()
