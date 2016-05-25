# -*- coding: utf-8 -*-

import string
import calendar

from cl.search.models import Docket, Opinion, OpinionCluster
from cl.citations.find_citations import get_citations
from cl.lib.import_lib import map_citations_to_models, find_person


# used to identify dates
# the order of these dates matters, as if there are multiple matches in an opinion for one type of date tag,
# the date associated to the --last-- matched tag will be the ones used for that type of date
FILED_TAGS = [
    'filed', 'opinion filed', 'date', 'order filed', 'delivered and filed', 'letter filed', 'dated', 'release date',
    'filing date', 'filed date', 'date submitted', 'as of', 'opinions filed', 'filed on', 'decision filed'
]
DECIDED_TAGS = ['decided', 'date decided', 'decided on', 'decided date']
ARGUED_TAGS = [
    'argued', 'submitted', 'submitted on briefs', 'on briefs', 'heard', 'considered on briefs',
    'argued and submitted', 'opinion', 'opinions delivered', 'opinion delivered', 'assigned on briefs',
    'opinion issued', 'delivered', 'rendered', 'considered on briefs on', 'opinion delivered and filed', 'orally argued',
    'rendered on', 'oral argument', 'submitted on record and briefs'
]
REARGUE_DENIED_TAGS = [
    'reargument denied', 'rehearing denied', 'further rehearing denied', 'as modified on denial of rehearing',
    'order denying rehearing', 'petition for rehearing filed', 'motion for rehearing filed',
    'rehearing denied to bar commission', 'reconsideration denied', 'denied', 'review denied',
    'motion for rehearing and/or transfer to supreme court denied', 'motion for reargument denied',
    'petition and crosspetition for review denied', 'opinion modified and as modified rehearing denied',
    'motion for rehearing andor transfer to supreme court denied', 'petition for rehearing denied',
    'leave to appeal denied', 'rehearings denied', 'motion for rehearing denied', 'second rehearing denied',
    'petition for review denied', 'appeal dismissed', 'rehearing en banc denied',
    'rehearing and rehearing en banc denied', 'order denying petition for rehearing',
    'all petitions for review denied', 'petition for allowance of appeal denied',
    'opinion modified and rehearing denied', 'as amended on denial of rehearing'
]
REARGUE_TAGS = ['reargued', 'reheard', 'upon rehearing', 'on rehearing']
CERT_GRANTED_TAGS = ['certiorari granted', 'petition and crosspetition for writ of certiorari granted']
CERT_DENIED_TAGS = [
    'certiorari denied', 'certiorari quashed', 'certiorari denied by supreme court',
    'petition for certiorari denied by supreme court'
]
UNKNOWN_TAGS = [
    'petition for review allowed', 'affirmed', 'reversed and remanded', 'rehearing overruled',
    'review granted', 'decision released', 'transfer denied', 'released for publication',
    'application to transfer denied', 'amended', 'reversed', 'opinion on petition to rehear',
    'suggestion of error overruled', 'cv', 'case stored in record room',
    'met to file petition for review disposed granted', 'rehearing granted', 'opinion released',
    'permission to appeal denied by supreme court', 'rehearing pending', 'application for transfer denied',
    'effective date', 'modified', 'opinion modified', 'transfer granted', 'discretionary review denied',
    'application for leave to file second petition for rehearing denied', 'final', 'date of judgment entry on appeal',
    'petition for review pending', 'writ denied', 'rehearing filed', 'as extended', 'officially released',
    'appendix filed', 'spring sessions', 'summer sessions', 'fall sessions', 'winter sessions',
    'discretionary review denied by supreme court', 'dissenting opinion', 'en banc reconsideration denied',
    'answer returned', 'refiled', 'revised', 'modified upon denial of rehearing', 'session mailed',
    'reversed and remanded with instructions', 'writ granted', 'date of judgment entry', 'preliminary ruling rendered',
    'amended on', 'dissenting opinion filed', 'concurring opinion filed', 'memorandum dated',
    'mandamus denied on mandate', 'updated', 'date of judgment entered', 'released and journalized', 'submitted on',
    'case assigned', 'opinion circulated for comment', 'submitted on rehearing',
    'united states supreme court dismissed appeal', 'answered', 'reconsideration granted in part and as amended',
    'as amended on denial of rehearing', 'reassigned', 'as amended', 'as corrected', 'writ allowed', 'released',
    'application for leave to appeal filed', 'affirmed on appeal reversed and remanded', 'as corrected',
    'withdrawn substituted and refiled', 'answered', 'released', 'as modified and ordered published', 'remanded',
    'concurring opinion added', 'decision and journal entry dated', 'memorandum filed', 'as modified'

]

# used to check if a docket number appears in what should be a citation string
# the order matters, as these are stripped from a docket string in order
DOCKET_JUNK = ['c.a. no. kc', 'c.a. no. pm', 'c.a. no.', 'i.c. no.', 'case no.', 'no.']

# known abbreviations that indicate if a citation isn't actually a citation
BAD_CITES = ['Iowa App.', 'R.I.Super.', 'Ma.Super.', 'Minn.App.', 'NCIC']

# used to figure out if a "citation text" is really a citation
TRIVIAL_CITE_WORDS = [n.lower() for n in calendar.month_name] + [n.lower()[:3] for n in calendar.month_name] + [
    'no'
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
                    print
                    print "Found unknown date tag '%s' with date '%s'." % date_info
                    print

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
            # if the docket number --is-- citation string, we're likely dealing with a somewhat common triplet of
            # (docket number, date, jurisdiction), which isn't a citation at all (so there's no problem)
            if item['docket']:
                docket_no = item['docket'].lower()
                if 'claim no.' in docket_no:
                    docket_no = docket_no.split('claim no.')[0]
                for junk in DOCKET_JUNK:
                    docket_no = docket_no.replace(junk, '')
                docket_no = docket_no.strip('.').strip()
                if docket_no and docket_no in c.lower():
                    continue
            # there are a trivial number of letters (except for months and a few trivial words) in the citation,
            # then it's not a citation at all
            non_trivial = c.lower()
            for trivial in TRIVIAL_CITE_WORDS:
                non_trivial = non_trivial.replace(trivial, '')
            num_letters = sum(non_trivial.count(letter) for letter in string.lowercase)
            if num_letters < 3:
                continue
            # if there is a string that's known to indicate a bad citation, then it's not a citation
            if any(bad in c for bad in BAD_CITES):
                continue
            # otherwise, this is a problem
            raise Exception("Failed to get a citation from the string '%s' in court '%s' with docket '%s'." % (
                c, item['court_id'], item['docket']
            ))
        else:
            found_citations.extend(found)
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
