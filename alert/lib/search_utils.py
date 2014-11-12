from urllib import urlencode
from urlparse import parse_qs
from django.utils.timezone import now

from alert.lib import sunburnt
from django.conf import settings


def make_get_string(request, nuke_fields=None):
    """Makes a get string from the request object. If necessary, it removes
    the pagination parameters.
    """
    if nuke_fields is None:
        nuke_fields = ['page']
    get_dict = parse_qs(request.META['QUERY_STRING'])
    for key in nuke_fields:
        try:
            del get_dict[key]
        except KeyError:
            pass
    get_string = urlencode(get_dict, True)
    if len(get_string) > 0:
        get_string += '&'
    return get_string


def get_string_to_dict(get_string):
    """Reverses the work that the make_get_string function performs, building a
    dict from the get_string.

    Used by alerts.
    """
    get_dict = {}
    for k, v in parse_qs(get_string).iteritems():
        get_dict[k] = v[0]
    return get_dict


def make_stats_variable(solr_facet_values, search_form):
    """Create a useful facet variable for use in a template

    This function merges the fields in the form with the facet values from
    Solr, creating useful variables for the front end.
    We need to handle two cases:
      1. The initial load of the page. For this we use the checked attr that
         is set on the form if there isn't a sort order in the request.
      2. The load after form submission. For this, we use the field.value().
    """
    facets = []
    solr_facet_values = dict(solr_facet_values['status_exact'])
    # Are any of the checkboxes checked?
    no_facets_selected = not any([field.value() for field in search_form
                                  if field.html_name.startswith('stat_')])
    for field in search_form:
        try:
            count = solr_facet_values[field.html_name.replace('stat_', '')]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the
            # facets variable
            continue

        if no_facets_selected:
            if field.html_name == 'stat_Precedential':
                checked = True
            else:
                checked = False
        else:
            if field.value() is True:
                checked = True
            else:
                checked = False

        facet = [
            field.label,
            field.html_name,
            count,
            checked,
            field.html_name.split('_')[1],
            field.field.widget.attrs['tabindex']
        ]
        facets.append(facet)
    return facets


def merge_form_with_courts(courts, search_form):
    """Merges the courts dict with the values from the search form.

    Final value is like (note that order is significant):
    courts = {
        'federal': [
            {'name': 'Eighth Circuit',
             'id': 'ca8',
             'checked': True,
             'jurisdiction': 'F',
             'has_oral_argument_scraper': True,
            },
            ...
        ],
        'district': [
            {'name': 'D. Delaware',
             'id': 'deld',
             'checked' False,
             'jurisdiction': 'FD',
             'has_oral_argument_scraper': False,
            },
            ...
        ],
        'state': [
            [{}, {}, {}][][]
        ],
        ...
    }

    State courts are a special exception. For layout purposes, they get
    bundled by supreme court and then by hand. Yes, this means new state courts
    requires manual adjustment here.
    """
    # Are any of the checkboxes checked?
    checked_statuses = [field.value() for field in search_form
                        if field.html_name.startswith('court_')]
    no_facets_selected = not any(checked_statuses)
    all_facets_selected = all(checked_statuses)
    court_count = len([status for status in checked_statuses if status is True])
    court_count_human = court_count
    if no_facets_selected or all_facets_selected:
        court_count_human = 'All'

    for field in search_form:
        if no_facets_selected:
            for court in courts:
                court['checked'] = True
        else:
            for court in courts:
                # We're merging two lists, so we have to do a nested loop
                # to find the right value.
                if 'court_%s' % court['pk'] == field.html_name:
                    court['checked'] = field.value()

    # Build the dict with jurisdiction keys and arrange courts into tabs
    court_tabs = {
        'federal': [],
        'district': [],
        'bankruptcy': [],
        'state': [],
        'special': [],
    }
    bap_bundle = []
    b_bundle = []
    state_bundle = []
    state_bundles = []
    for court in courts:
        if court['jurisdiction'] == 'F':
            court['tab'] = 'federal'
        elif court['jurisdiction'] == 'FD':
            court['tab'] = 'district'
        elif court['jurisdiction'] in ['FB', 'FBP']:
            court['tab'] = 'bankruptcy'
        elif court['jurisdiction'].startswith('S'):
            court['tab'] = 'state'  # Merge all state courts.
        elif court['jurisdiction'] in ['FS', 'C']:
            court['tab'] = 'special'

        if court['tab'] == 'bankruptcy':
            # Bankruptcy gets bundled into BAPs and regular courts.
            if court['jurisdiction'] == 'FBP':
                bap_bundle.append(court)
            else:
                b_bundle.append(court)
        elif court['tab'] == 'state':
            # State courts get bundled by supreme courts
            if court['jurisdiction'] == 'S':
                # Whenever we hit a state supreme court, we append the
                # previous bundle and start a new one.
                if state_bundle:
                    state_bundles.append(state_bundle)
                state_bundle = [court]
            else:
                state_bundle.append(court)
        else:
            court_tabs[court['tab']].append(court)
    state_bundles.append(state_bundle)  # appends the final state bundle after the loop ends. Hack?

    # Put the bankruptcy bundles in the courts dict
    court_tabs['bankruptcy'].append(bap_bundle)
    court_tabs['bankruptcy'].append(b_bundle)

    # Divide the state bundles into the correct partitions
    court_tabs['state'].append(state_bundles[:15])
    court_tabs['state'].append(state_bundles[15:34])
    court_tabs['state'].append(state_bundles[34:])

    return court_tabs, court_count_human, court_count


def make_fq(cd, field, key):
    """Does some minimal processing of the query string to get it into a
    proper field query.

    This is necessary because despite our putting AND as the default join
    method, in some cases Solr decides OR is a better approach. So, to work
    around this bug, we do some minimal query parsing ourselves (ugh!).
    """
    if '"' in cd[key]:
        fq = '%s:(%s)' % (field, cd[key])
    else:
        fq = '%s:(%s)' % (field, ' AND '.join(cd[key].split()))
    return fq


def make_date_query(query_field, before, after):
    """Given the cleaned data from a form, return a valid Solr fq string"""
    if any([before, after]):
        if hasattr(after, 'strftime'):
            date_filter = '[%sT00:00:00Z TO ' % after.isoformat()
        else:
            date_filter = '[* TO '
        if hasattr(before, 'strftime'):
            date_filter = '%s%sT23:59:59Z]' % (date_filter, before.isoformat())
        else:
            date_filter = '%s*]' % date_filter
    else:
        # No date filters were requested
        return ""
    return '%s:%s' % (query_field, date_filter)


def make_cite_count_query(cd):
    """Given the cleaned data from a form, return a valid Solr fq string"""
    start = cd['cited_gt']
    end = cd['cited_lt']
    if start or end:
        return 'citeCount:[%s TO %s]' % (start, end)
    else:
        return ""


def get_selected_field_string(cd, prefix):
    """Pulls the selected checkboxes out of the form data, and puts it into
    Solr strings. Uses a prefix to know which items to pull out of the cleaned
    data. Check forms.py to see how the prefixes are set up.

    Final strings are of the form "A" OR "B" OR "C", with quotes in case there
    are spaces in the values.
    """
    selected_fields = ['"%s"' % k.replace(prefix, '')
                       for k, v in cd.iteritems()
                       if (k.startswith(prefix) and v is True)]

    selected_field_string = ' OR '.join(selected_fields)
    return selected_field_string

qf = {
    'text': 1.0,
    'dateFiled': 1.0,
    'court': 1.0,
    'caseName': 3,
    'docketNumber': 1.0,
    'westCite': 1.0,
    'neutralCite': 1.0,
    'lexisCite': 1.0,
    'status': 1.25,
    'caseNumber': 1.25,
}


def make_qf_string(qf):
    qf_array = []
    for k, v in qf.iteritems():
        qf_array.append('%s^%s' % (k, v))
    return ' '.join(qf_array)


def build_main_query(cd, highlight='all', order_by=''):
    main_params = {
        'q': cd['q'] or '*:*',
        'sort': cd.get('order_by', order_by),
        'caller': 'build_main_query',
    }

    if str(main_params['sort']).startswith('score') and \
            cd['type'] == 'o':
        main_params['boost'] = 'pagerank'

    # Give a boost on the case_name field if it's obviously a case_name query.
    vs_query = any([' v ' in main_params['q'],
                    ' v. ' in main_params['q'],
                    ' vs. ' in main_params['q']])
    in_re_query = main_params['q'].lower().startswith('in re ')
    matter_of_query = main_params['q'].lower().startswith('matter of ')
    ex_parte_query = main_params['q'].lower().startswith('ex parte ')
    if any([vs_query, in_re_query, matter_of_query, ex_parte_query]):
        qf.update({'caseName': 50})
        main_params['qf'] = make_qf_string(qf)

    if highlight:
        # Common highlighting params up here.
        main_params.update({
            'hl': 'true',
            'f.text.hl.snippets': '5',
            'f.text.hl.maxAlternateFieldLength': '500',
            'f.text.hl.alternateField': 'text',
        })

        if highlight == 'all':
            # Requested fields for the main query. We only need the fields
            # here that are not requested as part of highlighting. Facet
            # params are not set here because they do not retrieve results,
            # only counts (they are set to 0 rows).
            common_fl = ['id', 'absolute_url', 'court_id',
                          'local_path', 'source', 'download_url']
            common_hlfl = ['text', 'caseName', 'judge', 'docketNumber',
                            'court_citation_string']

            if cd['type'] == 'o':
                main_params.update({
                    'fl': ','.join(common_fl + ['status', 'dateFiled',
                                                 'citeCount']),
                    'hl.fl': ','.join(common_hlfl +
                                      ['suitNature', 'citation', 'neutralCite',
                                       'lexisCite']),
                    'f.suitNature.hl.fragListBuilder': 'single',
                    'f.citation.hl.fragListBuilder': 'single',
                    'f.neutralCite.hl.fragListBuilder': 'single',
                    'f.lexisCite.hl.fragListBuilder': 'single',
                    'f.suitNature.hl.alternateField': 'suitNature',
                    'f.citation.hl.alternateField': 'citation',
                    'f.neutralCite.hl.alternateField': 'neutralCite',
                    'f.lexisCite.hl.alternateField': 'lexisCite',
                })
            elif cd['type'] == 'oa':
                main_params.update({
                    'fl': ','.join(common_fl + ['docket_id', 'dateArgued', 'duration']),
                    'hl.fl': ','.join(common_hlfl),
                })
            main_params.update({
                'f.caseName.hl.fragListBuilder': 'single',
                'f.judge.hl.fragListBuilder': 'single',
                'f.docketNumber.hl.fragListBuilder': 'single',
                'f.court_citation_string.hl.fragListBuilder': 'single',

                # If there aren't any hits in the text return the field instead
                'f.caseName.hl.alternateField': 'caseName',
                'f.judge.hl.alternateField': 'judge',
                'f.docketNumber.hl.alternateField': 'docketNumber',
                'f.court_citation_string.hl.alternateField': 'court_citation_string',
            })
        elif highlight == 'text':
            main_params['hl.fl'] = 'text'
    else:
        # highlighting is off, therefore we get the default fl parameter,
        # which gives us all fields. We could set it manually, but there's
        # no need.
        pass

    # Changes here are usually mirrored in place_facet_queries, below.
    main_fq = []

    if cd['case_name']:
        main_fq.append(make_fq(cd, 'caseName', 'case_name'))
    if cd['judge']:
        main_fq.append(make_fq(cd, 'judge', 'judge'))
    if cd['docket_number']:
        main_fq.append(make_fq(cd, 'docketNumber', 'docket_number'))

    if cd['type'] == 'o':
        if cd['citation']:
            main_fq.append(make_fq(cd, 'citation', 'citation'))
        if cd['neutral_cite']:
            main_fq.append(make_fq(cd, 'neutralCite', 'neutral_cite'))
        main_fq.append(make_date_query('dateFiled', cd['filed_before'],
                                       cd['filed_after']))

        # Citation count
        cite_count_query = make_cite_count_query(cd)
        main_fq.append(cite_count_query)
    elif cd['type'] == 'oa':
        main_fq.append(make_date_query('dateArgued', cd['argued_before'],
                                       cd['argued_after']))

    # Facet filters
    selected_courts_string = get_selected_field_string(cd, 'court_')
    if cd['type'] == 'o':
        selected_stats_string = get_selected_field_string(cd, 'stat_')
        if len(selected_courts_string) + len(selected_stats_string) > 0:
            main_fq.extend([
                '{!tag=dt}status_exact:(%s)' % selected_stats_string,
                '{!tag=dt}court_exact:(%s)' % selected_courts_string
            ])
    elif cd['type'] == 'oa':
        if len(selected_courts_string) > 0:
            main_fq.extend([
                '{!tag=dt}court_exact:(%s)' % selected_courts_string
            ])

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(main_fq) > 0:
        main_params['fq'] = main_fq

    #print "Params sent to search are: %s" % '&'.join(['%s=%s' % (k, v) for k, v in main_params.items()])
    #print results_si.execute()
    return main_params


def place_facet_queries(cd, conn=sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')):
    """Get facet values for the status filters

    Using the search form, query Solr and get the values for the status filters.
    """
    # Build up all the queries needed
    facet_params = {
        'rows': '0',
        'facet': 'true',
        'facet.mincount': 0,
        'facet.field': '{!ex=dt}status_exact',
        'q': cd['q'] or '*:*',
        'caller': 'facet_parameters',
    }
    fq = []

    # Case Name and judges
    if cd['case_name']:
        fq.append(make_fq(cd, 'caseName', 'case_name'))
    if cd['judge']:
        fq.append(make_fq(cd, 'judge', 'judge'))

    # Citations
    if cd['citation']:
        fq.append(make_fq(cd, 'citation', 'citation'))
    if cd['docket_number']:
        fq.append(make_fq(cd, 'docketNumber', 'docket_number'))
    if cd['neutral_cite']:
        fq.append(make_fq(cd, 'neutralCite', 'neutral_cite'))

    fq.append(make_date_query('dateFiled', cd['filed_before'], cd['filed_after']))
    fq.append(make_cite_count_query(cd))

    # Faceting
    selected_courts_string = get_selected_field_string(cd, 'court_')  # Status facets depend on court checkboxes
    selected_stats_string = get_selected_field_string(cd, 'stat_')
    if len(selected_stats_string) > 0:
        fq.extend(['{!tag=dt}status_exact:(%s)' % selected_stats_string,
                   'court_exact:(%s)' % selected_courts_string])

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(fq) > 0:
        facet_params['fq'] = fq

    stat_facet_fields = conn.raw_query(**facet_params).execute().facet_counts.facet_fields

    return stat_facet_fields


def get_court_start_year(conn, court):
    """Get the start year for a court by placing a Solr query. If a court is
    active, but does not yet have any results, return the current year.
    """
    if court.lower() == 'all':
        params = {'sort': 'dateFiled asc', 'rows': 1, 'q': '*:*'}
    else:
        params = {'fq': ['court_exact:%s' % court], 'sort': 'dateFiled asc', 'rows': 1}
    params['caller'] = 'search_utils'
    response = conn.raw_query(**params).execute()
    try:
        year = response.result.docs[0]['dateFiled'].year
    except IndexError:
        # Occurs when there are 0 results for an active court (rare but possible)
        year = now().year

    return year


def build_coverage_query(court, start_year):
    params = {
        'facet': 'true',
        'facet.range': 'dateFiled',
        'facet.range.start': '%d-01-01T00:00:00Z' % start_year,
        'facet.range.end': 'NOW/DAY',
        'facet.range.gap': '+1YEAR',
        'rows': 0,
        'q': '*:*',  # Without this, results will be omitted.
        'caller': 'build_coverage_query',
    }
    if court.lower() != 'all':
        params['fq'] = ['court_exact:%s' % court]
    return params


def build_court_count_query():
    """Build a query that returns the count of cases for all courts"""
    params = {
        'facet': 'true',
        'facet.field': 'court_exact',
        'facet.limit': -1,
        'rows': 0,
        'caller': 'build_court_count_query',
    }
    return params


def build_total_count_query():
    """Build a query that returns the total result count as quickly as possible."""
    params = {
        'rows': 0,
        'q': '*:*',
        'caller': 'build_total_count_query',
    }
    return params
