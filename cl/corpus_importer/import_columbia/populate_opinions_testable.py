# -*- coding: utf-8 -*-

# just a script used to see what the objects -should- look like when instantiated as dictionaries, for testing
# the main script

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


def make_objects(item):
    """Takes the case data <item> and associates it with objects.

    Returns a (Docket, OpinionCluster, Opinion, Opinion, ...) list.
    The objects' save method should be called in the same order as they are returned.
    """
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

    # instantiate docket object
    docket = {
        'date_created': 'now function',
        'date_modified': 'now function',
        'date_argued': argued_date,
        'date_reargued': reargued_date,
        'date_reargument_denied': reargue_denied_date,
        'court_id': item.get('court_id'),
        'case_name_short': item.get('case_name_short'),
        'case_name': item.get('case_name'),
        'case_name_full': item.get('case_name_full'),
        'docket_number': item.get('docket')
    }

    # grab citations in, e.g. the {'federal_cite_one': '1 U.S. 1', ...} form
    # will be passed as kwargs
    # all_citations = map_citations_to_models(item['citation'])

    # instantiate opinion cluster object
    cluster = {
        'precedential_status': ('Unpublished' if item['unpublished'] else 'Published'),
        'docket': docket,
        'date_created': 'now function',
        'date_modified': 'now function',
        'date_filed': opinion_date, 
        'panel': item.get('panel', []),
        'case_name_short': item.get('case_name_short'),
        'case_name': item.get('case_name'),
        'case_name_full': item.get('case_name_full'),
        'source': 'Z (columbia archive)',
        'attorneys': item.get('attorneys'),
        'posture': item.get('posture')
        # **all_citations
    }

    # create opinion, concurrence, and dissent objects
    opinions = []
    for opinion_info in item['opinions']:
        opinions.append({
            'cluster': cluster,
            'author': opinion_info['byline'],
            'date_created': 'now function',
            'date_modified': 'now function',
            'type': OPINION_TYPE_MAPPING[opinion_info['type']],
            'html_columbia': opinion_info['opinion']
        })
        
    return [docket, cluster] + opinions


if __name__ == '__main__':
    import parse_opinions
    for parsed in parse_opinions.parse_many("../data/", limit=100, court_fallback_regex=r"data/([a-z_]+?/[a-z_]+?)/"):
        case_objects = make_objects(parsed)
        pass
        # for object in case_objects:
        #     object.save()