# -*- coding: utf-8 -*-

from cl.search.models import Docket, Opinion, OpinionCluster
from cl.citations.find_citations import get_citations
from cl.lib.import_lib import map_citations_to_models, find_person


# used to identify dates
FILED_TAGS = [
    'filed', 'opinion filed', 'date', 'order filed', 'delivered and filed', 'letter filed', 'dated', 'release date',
    'filing date', 'filed date', 'date submitted', 'as of'
]
DECIDED_TAGS = ['decided', 'date decided']
ARGUED_TAGS = [
    'argued', 'submitted', 'submitted on briefs', 'on briefs', 'heard', 'considered on briefs',
    'argued and submitted', 'opinion', 'opinions delivered', 'opinion delivered', 'assigned on briefs',
    'opinion issued', 'delivered', 'rendered', 'considered on briefs on', 'opinion delivered and filed', 'orally argued'
]
REARGUE_DENIED_TAGS = [
    'reargument denied', 'rehearing denied', 'further rehearing denied', 'as modified on denial of rehearing',
    'order denying rehearing', 'petition for rehearing filed', 'motion for rehearing filed',
    'rehearing denied to bar commission', 'reconsideration denied', 'denied', 'review denied',
    'motion for rehearing and/or transfer to supreme court denied', 'motion for reargument denied',
    'petition and crosspetition for review denied', 'opinion modified and as modified rehearing denied',
    'motion for rehearing andor transfer to supreme court denied', 'petition for rehearing denied',
    'leave to appeal denied', 'rehearings denied', 'motion for rehearing denied', 'second rehearing denied',
    'petition for review denied'
]
REARGUE_TAGS = ['reargued', 'reheard', 'upon rehearing', 'on rehearing']
CERT_GRANTED_TAGS = ['certiorari granted']
CERT_DENIED_TAGS = ['certiorari denied', 'certiorari quashed', 'certiorari denied by supreme court']
UNKNOWN_TAGS = [
    'petition for review allowed', 'affirmed', 'reversed and remanded', 'rehearing overruled',
    'review granted', 'decision released', 'transfer denied', 'released for publication',
    'application to transfer denied', 'amended', 'reversed', 'opinion on petition to rehear',
    'suggestion of error overruled', 'cv', 'case stored in record room',
    'met to file petition for review disposed granted', 'rehearing granted', 'opinion released',
    'permission to appeal denied by supreme court', 'rehearing pending', 'application for transfer denied',
    'effective date', 'modified', 'opinion modified', 'transfer granted', 'no', 'discretionary review denied',
    'application for leave to file second petition for rehearing denied', 'final', 'date of judgment entry on appeal',
    'petition for review pending', 'writ denied', 'rehearing filed', 'as extended', 'officially released',
    'appendix filed', 'spring sessions'

]

# used to map the parsed opinion types to their tags in the populated opinion objects
OPINION_TYPE_MAPPING = {
    'opinion': '020lead'
    ,'dissent': '040dissent'
    ,'concurrence': '030concurrence'
}

def make_and_save(item):
    """Associates case data from `parse_opinions` with objects. Saves these objects."""
    date_filed = date_argued = date_reargued = date_reargument_denied = date_cert_granted = date_cert_denied = None
    unknown_date = None
    for date_cluster in item['dates']:
        for date_info in date_cluster:
            # check for any dates that clearly aren't dates
            if date_info[1].year < 1600 or date_info[1].year > 2020:
                continue
            # check for untagged dates that will be assigned to date_filed
            if date_info[0] is None:
                date_filed = date_info[1]
                continue
            # try to figure out what type of date it is based on its tag string
            if date_info[0] in FILED_TAGS:
                date_filed = date_info[1]
            elif date_info[0] in DECIDED_TAGS:
                if not date_filed:
                    date_filed = date_info[1]
            elif date_info[0] in ARGUED_TAGS:
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
                unknown_date = date_info[1]
                if date_info[0] not in UNKNOWN_TAGS:
                    print "Found unknown date tag '%s' with date '%s'." % date_info

    # the main date (used for date_filed in OpinionCluster) and panel dates (used for finding judges) are ordered in
    # terms of which type of dates best reflect them
    main_date = date_filed or date_argued or date_reargued or date_reargument_denied or unknown_date
    panel_date = date_argued or date_reargued or date_reargument_denied or date_filed or unknown_date

    docket = Docket(
        source=Docket.DEFAULT
        ,date_argued=date_argued
        ,date_reargued=date_reargued
        ,date_cert_granted=date_cert_granted
        ,date_cert_denied=date_cert_denied
        ,date_reargument_denied=date_reargument_denied
        ,court_id=item['court_id']
        ,case_name_short=item['case_name_short'] or ''
        ,case_name=item['case_name'] or ''
        ,case_name_full=item['case_name_full'] or ''
        ,docket_number=item['docket'] or ''
    )
    docket.save()

    # get citations in the form of, e.g. {'federal_cite_one': '1 U.S. 1', ...}
    found_citations = []
    for c in item['citations']:
        found = get_citations(c)
        if not found:
            raise Exception("Failed to get a citation from the string '%s'." % c)
        elif len(found) > 1:
            raise Exception("Got multiple citations from string '%s' when there should have been one." % c)
        found_citations.append(found[0])
    citations_map = map_citations_to_models(found_citations)

    cluster = OpinionCluster(
        docket=docket
        ,precedential_status=('Unpublished' if item['unpublished'] else 'Published')
        ,date_filed=main_date
        ,case_name_short=item['case_name_short'] or ''
        ,case_name=item['case_name'] or ''
        ,case_name_full=item['case_name_full'] or ''
        ,source='Z'
        ,attorneys=item['attorneys'] or ''
        ,posture=item['posture'] or ''
        ,**citations_map
    )
    cluster.save()

    panel = [find_person(n, item['court_id'], case_date=panel_date) for n in item['panel']]
    panel = [x for x in panel if x is not None]
    for member in panel:
        cluster.panel.add(member)

    for opinion_info in item['opinions']:
        if opinion_info['author'] is None:
            author = None
        else:
            author = find_person(opinion_info['author'], item['court_id'], case_date=panel_date)
        opinion = Opinion(
            cluster=cluster
            ,author=author
            ,per_curiam=opinion_info['per_curiam']
            ,type=OPINION_TYPE_MAPPING[opinion_info['type']]
            ,html_columbia=opinion_info['opinion']
        )
        opinion.save()
        joined_by = [find_person(n, item['court_id'], case_date=panel_date) for n in opinion_info['joining']]
        joined_by = [x for x in joined_by if x is not None]
        for joiner in joined_by:
            opinion.joined_by.add(joiner)
