import datetime
from urllib import urlencode
from urlparse import parse_qs
from django.utils.timezone import now

from alert.lib import sunburnt
from django.conf import settings


def make_get_string(request):
    """Makes a get string from the request object. If necessary, it removes
    the pagination parameters.
    """
    get_dict = parse_qs(request.META['QUERY_STRING'])
    try:
        del get_dict['page']
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


def make_facets_variable(solr_facet_values, search_form, solr_field, prefix):
    """Create a useful facet variable for use in a template

    This function merges the fields in the form with the facet values from
    Solr, creating useful variables for the front end.
    We need to handle two cases:
      1. The initial load of the page. For this we use the checked attr that
         is set on the form if there isn't a sort order in the request.
      2. The load after form submission. For this, we use the field.value().
    """
    facets = []
    solr_facet_values = dict(solr_facet_values[solr_field])
    # Are any of the checkboxes checked?
    no_facets_selected = not any([field.value() for field in search_form
                                  if field.html_name.startswith(prefix)])
    for field in search_form:
        try:
            count = solr_facet_values[field.html_name.replace(prefix, '')]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the
            # facets variable
            continue

        if no_facets_selected:
            if prefix == 'stat_':
                if field.html_name == 'stat_Precedential':
                    checked = True
                else:
                    checked = False
            else:
                checked = True
        else:
            if field.value() is True:
                checked = True
            else:
                checked = False

        facet = [field.label,
                 field.html_name,
                 count,
                 checked,
                 field.html_name.split('_')[1]]
        facets.append(facet)
    return facets


def make_date_query(cd):
    """Given the cleaned data from a form, return a valid Solr fq string"""
    before = cd['filed_before']
    after = cd['filed_after']
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
    return 'dateFiled:%s' % date_filter

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


def build_main_query(cd, highlight=True):
    main_params = {}
    # Build up all the queries needed
    main_params['q'] = cd['q'] or '*:*'

    # Sorting for the main query
    main_params['sort'] = cd.get('sort', '')
    
    # if user choose "Relevance"(the sort param will start with 'score'), then
    # "&defType=edismax&boost=pagerank" will be added to the URL, which means boosting with pagerank.
    if str(main_params['sort']).startswith('score'):
        main_params['defType'] = 'edismax'
        main_params['boost'] = 'pagerank'

    if highlight:
        # Requested fields for the main query. We only need the fields here that
        # are not requested as part of highlighting. Facet params are not set
        # here because they do not retrieve results, only counts (they are set
        # to 0 rows).
        main_params['fl'] = 'id,absolute_url,court_id,local_path,source,download_url,status,dateFiled,citeCount'

        # Highlighting for the main query.
        main_params['hl'] = 'true'
        main_params['hl.fl'] = 'text,caseName,judge,suitNature,citation,neutralCite,docketNumber,lexisCite,court_citation_string'
        main_params['f.caseName.hl.fragListBuilder'] = 'single'
        main_params['f.judge.hl.fragListBuilder'] = 'single'
        main_params['f.suitNature.hl.fragListBuilder'] = 'single'
        main_params['f.citation.hl.fragListBuilder'] = 'single'
        main_params['f.neutralCite.hl.fragListBuilder'] = 'single'
        main_params['f.docketNumber.hl.fragListBuilder'] = 'single'
        main_params['f.lexisCite.hl.fragListBuilder'] = 'single'
        main_params['f.court_citation_string.hl.fragListBuilder'] = 'single'
        main_params['f.text.hl.snippets'] = '5'
        # If there aren't any hits in the text return the field instead
        main_params['f.text.hl.alternateField'] = 'text'
        main_params['f.text.hl.maxAlternateFieldLength'] = '500'
        main_params['f.caseName.hl.alternateField'] = 'caseName'
        main_params['f.judge.hl.alternateField'] = 'judge'
        main_params['f.suitNature.hl.alternateField'] = 'suitNature'
        main_params['f.citation.hl.alternateField'] = 'citation'
        main_params['f.neutralCite.hl.alternateField'] = 'neutralCite'
        main_params['f.docketNumber.hl.alternateField'] = 'docketNumber'
        main_params['f.lexisCite.hl.alternateField'] = 'lexisCite'
        main_params['f.court_citation_string.hl.alternateField'] = 'court_citation_string'
    else:
        # highlighting is off, therefore we get the default fl parameter,
        # which gives us all fields. We could set it manually, but there's
        # no need.
        pass

    main_fq = []
    # Case Name and judges
    if cd['case_name']:
        main_fq.append('caseName:(%s)' % " AND ".join(cd['case_name'].split()))
    if cd['judge']:
        main_fq.append('judge:(%s)' % ' AND '.join(cd['judge'].split()))

    # Citations
    if cd['citation']:
        main_fq.append('citation:(%s)' % ' AND '.join(cd['citation'].split()))
    if cd['docket_number']:
        main_fq.append('docketNumber:(%s)' % ' AND '.join(cd['docket_number'].split()))
    if cd['neutral_cite']:
        main_fq.append('neutralCite:(%s)' % ' AND '.join(cd['neutral_cite'].split()))

    # Dates
    date_query = make_date_query(cd)
    main_fq.append(date_query)

    # Citation count
    cite_count_query = make_cite_count_query(cd)
    main_fq.append(cite_count_query)

    # Facet filters
    selected_courts_string = get_selected_field_string(cd, 'court_')
    selected_stats_string = get_selected_field_string(cd, 'stat_')
    if len(selected_courts_string) + len(selected_stats_string) > 0:
        main_fq.extend(['{!tag=dt}status_exact:(%s)' % selected_stats_string,
                        '{!tag=dt}court_exact:(%s)' % selected_courts_string])

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(main_fq) > 0:
        main_params['fq'] = main_fq

    # For debugging:
    #print "Params sent to search are: %s" % '&'.join(['%s=%s' % (k, v) for k, v in main_params.items()])
    #print results_si.execute()
    return main_params


def place_facet_queries(cd):
    """Get facet values for the court and status filters

    Using the search form, query Solr and get the values for the court and
    status filters. Both of these need to be queried in a single function b/c
    they are dependent on each other. For example, when you filter using one,
    you need to change the values of the other.
    """
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    shared_facet_params = {}
    court_facet_params = {}
    stat_facet_params = {}

    # Build up all the queries needed
    shared_facet_params['q'] = cd['q'] or '*:*'

    shared_fq = []
    court_fq = []
    stat_fq = []
    # Case Name
    if cd['case_name'] != '' and cd['case_name'] is not None:
        shared_fq.append('caseName:(%s)' % " AND ".join(cd['case_name'].split()))
    if cd['judge']:
        shared_fq.append('judge:(%s)' % ' AND '.join(cd['judge'].split()))

    # Citations
    if cd['citation']:
        shared_fq.append('citation:%s' % cd['citation'])
    if cd['docket_number']:
        shared_fq.append('docketNumber:%s' % cd['docket_number'])
    if cd['neutral_cite']:
        shared_fq.append('neutralCite:%s' % cd['neutral_cite'])

    # Dates
    date_query = make_date_query(cd)
    shared_fq.append(date_query)

    # Citation count
    cite_count_query = make_cite_count_query(cd)
    shared_fq.append(cite_count_query)

    # Faceting
    shared_facet_params['rows'] = '0'
    shared_facet_params['facet'] = 'true'
    shared_facet_params['facet.mincount'] = 0
    court_facet_params['facet.field'] = '{!ex=dt}court_exact'
    stat_facet_params['facet.field'] = '{!ex=dt}status_exact'
    selected_courts_string = get_selected_field_string(cd, 'court_')
    selected_stats_string = get_selected_field_string(cd, 'stat_')
    if len(selected_courts_string) > 0:
        court_fq.extend(['{!tag=dt}court_exact:(%s)' % selected_courts_string,
                         'status_exact:(%s)' % selected_stats_string])
    if len(selected_stats_string) > 0:
        stat_fq.extend(['{!tag=dt}status_exact:(%s)' % selected_stats_string,
                        'court_exact:(%s)' % selected_courts_string])

    # Add the shared fq values to each parameter value
    court_fq.extend(shared_fq)
    stat_fq.extend(shared_fq)

    # If a param has been added to the fq variables, then we add them to the
    # main_params var. Otherwise, we don't, as doing so throws an error.
    if len(court_fq) > 0:
        court_facet_params['fq'] = court_fq
    if len(stat_fq) > 0:
        stat_facet_params['fq'] = stat_fq

    # We add shared parameters to each parameter variable
    court_facet_params.update(shared_facet_params)
    stat_facet_params.update(shared_facet_params)

    court_response = conn.raw_query(**court_facet_params).execute()
    count = court_response.result.numFound
    court_facet_fields = court_response.facet_counts.facet_fields
    stat_facet_fields = conn.raw_query(**stat_facet_params).execute().facet_counts.facet_fields

    return court_facet_fields, stat_facet_fields, count


def get_court_start_year(conn, court):
    """Get the start year for a court by placing a Solr query. If a court is
    active, but does not yet have any results, return the current year.
    """
    if court.lower() == 'all':
        params = {'sort': 'dateFiled asc', 'rows': 1, 'q': '*:*'}
    else:
        params = {'fq': ['court_exact:%s' % court], 'sort': 'dateFiled asc', 'rows': 1}
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
    }
    if court.lower() != 'all':
        params['fq'] = ['court_exact:%s' % court]
    return params


def build_court_count_query():
    """Build a query that returns the count of cases for all courts"""
    params = {
        'facet': 'true',
        'facet.field': 'court_exact',
        'rows': 0,
        'q': '*:*',
    }
    return params
