# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from urllib import urlencode
from urlparse import parse_qs

from alert.lib import sunburnt
from django.conf import settings
from django.contrib import messages


def make_get_string(request):
    '''Makes a get string from the request object. If necessary, it removes 
    the pagination parameters.'''
    get_dict = parse_qs(request.META['QUERY_STRING'])
    try:
        del get_dict['page']
    except KeyError:
        pass
    get_string = urlencode(get_dict, True)
    if len(get_string) > 0:
        get_string = get_string + '&'
    return get_string

def make_facets_variable(solr_facet_values, search_form, solr_field, prefix):
    '''Create a useful facet variable for use in a template
    
    This function merges the fields in the form with the facet values from Solr, 
    creating useful variables for the front end.
    We need to handle two cases:
      1. The initial load of the page. For this we use the checked attr that 
         is set on the form if there isn't a sort order in the request.
      2. The load after form submission. For this, we use the field.value().
    '''
    facets = []
    solr_facet_values = dict(solr_facet_values[solr_field])
    for field in search_form:
        try:
            count = solr_facet_values[field.html_name.replace(prefix, '')]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the 
            # facets variable
            continue

        try:
            refine = search_form['refine'].value()
        except KeyError:
            # Happens on page load, since the field doesn't exist yet.
            refine = 'new'

        if refine == 'new':
            checked = True
        else:
            # It's a refinement
            if field.value() == 'on':
                checked = True
            else:
                checked = False

        facet = [field.label,
                 field.html_name,
                 count,
                 checked]
        facets.append(facet)
    return facets

def make_date_query(cd, request=None):
    '''Given the cleaned data from a form, return a valid Solr fq string'''
    before = cd['filed_before']
    after = cd['filed_after']

    try:
        if after > before:
            if request:
                # We don't always want to create a message. Only do this if the
                # caller sets the request var.
                message = 'You\'ve requested all documents before %s and after\
                           %s. Since %s comes before %s, these filters cannot \
                           not be used' % (before.date(),
                                           after.date(),
                                           before.date(),
                                           after.date())
                messages.add_message(request, messages.INFO, message)
            return ''
    except TypeError:
        # Happens when one of the inputs isn't a date
        pass
    if hasattr(after, 'strftime'):
        date_filter = '{%sZ TO ' % after.isoformat()
    else:
        date_filter = '{* TO '
    if hasattr(before, 'strftime'):
        date_filter = '%s%sZ}' % (date_filter, before.isoformat())
    else:
        date_filter = '%s*}' % date_filter
    return 'dateFiled:%s' % date_filter

def get_selected_field_string(cd, prefix):
    '''Pulls the selected checkboxes out of the form data, and puts it into Solr
    strings. Uses a prefix to know which items to pull out of the cleaned data.
    Check forms.py to see how the prefixes are set up.
    '''
    selected_fields = [k.replace(prefix, '')
                       for k, v in cd.iteritems()
                       if (k.startswith(prefix) and v == True)]

    selected_field_string = ' OR '.join(selected_fields)
    return selected_field_string

def place_main_query(request, search_form):
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    main_params = {}
    if search_form.is_valid():
        cd = search_form.cleaned_data

        # Build up all the queries needed
        main_params['q'] = cd['q']

        # Sorting for the main query
        main_params['sort'] = request.GET.get('sort', '')

        # Requested fields for the main query. We only need the fields here that
        # are not requested as part of highlighting. Facet params are not set 
        # here because they do not retrieve results, only counts (they are set
        # to 0 rows).
        main_params['fl'] = 'id,absolute_url,court_id,local_path,source,download_url,status,dateFiled'

        # Highlighting for the main query.
        main_params['hl'] = 'true'
        main_params['hl.fl'] = 'text,caseName,westCite,docketNumber,lexisCite,court_citation_string'
        main_params['hl.snippets'] = '5'
        main_params['hl.maxAnalyzedChars'] = '150000'
        # If there aren't any hits in the text return the field instead
        main_params['f.text.hl.alternateField'] = 'text'
        main_params['f.text.hl.maxAlternateFieldLength'] = '500'
        main_params['f.caseName.hl.alternateField'] = 'caseName'
        main_params['f.westCite.hl.alternateField'] = 'westCite'
        main_params['f.docketNumber.hl.alternateField'] = 'docketNumber'
        main_params['f.lexisCite.hl.alternateField'] = 'lexisCite'
        main_params['f.court_citation_string.hl.alternateField'] = 'court_citation_string'

        main_fq = []
        # Case Name
        if cd['case_name'] != '':
            main_fq.append('caseName:' + cd['case_name'])

        # Citations
        if cd['west_cite'] != '':
            main_fq.append('westCite:' + cd['west_cite'])
        if cd['docket_number'] != '':
            main_fq.append('docketNumber:' + cd['docket_number'])

        # Dates
        date_query = make_date_query(cd, request)
        main_fq.append(date_query)

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

    else:
        print "The form is invalid or unbound."
        #TODO: Remove before sending live
        main_params['q'] = '*'

    # For debugging:
    #print "Params sent to search are: %s" % '&'.join(['%s=%s' % (k, v) for k, v in main_params.items()])
    #print results_si.execute()
    return conn.raw_query(**main_params)

def place_facet_queries(search_form):
    '''Get facet values for the court and status filters
    
    Using the search form, query Solr and get the values for the court and 
    status filters. Both of these need to be queried in a single function b/c
    they are dependent on each other. For example, when you filter using one,
    you need to change the values of the other.
    '''
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    shared_facet_params = {}
    court_facet_params = {}
    stat_facet_params = {}
    if search_form.is_valid():
        cd = search_form.cleaned_data

        # Build up all the queries needed
        shared_facet_params['q'] = cd['q']

        shared_fq = []
        court_fq = []
        stat_fq = []
        # Case Name
        if cd['case_name'] != '':
            shared_fq.append('caseName:' + cd['case_name'])

        # Citations
        if cd['west_cite'] != '':
            shared_fq.append('westCite:' + cd['west_cite'])
        if cd['docket_number'] != '':
            shared_fq.append('docketNumber:' + cd['docket_number'])

        # Dates
        date_query = make_date_query(cd)
        shared_fq.append(date_query)

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

    court_facet_fields = conn.raw_query(**court_facet_params).execute().facet_counts.facet_fields
    stat_facet_fields = conn.raw_query(**stat_facet_params).execute().facet_counts.facet_fields

    # Create facet variables that can be used in our templates
    court_facets = make_facets_variable(
                     court_facet_fields, search_form, 'court_exact', 'court_')
    status_facets = make_facets_variable(
                     stat_facet_fields, search_form, 'status_exact', 'stat_')

    return court_facets, status_facets
