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

from alert.alerts.forms import CreateAlertForm
from alert.lib import sunburnt
from alert.search.forms import SearchForm
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.paginator import PageNotAnInteger
from django.core.paginator import EmptyPage
from django.conf import settings
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext
from django.utils.datastructures import MultiValueDictKeyError

conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')

def get_date_filed_or_return_zero(doc):
    """Used for sorting dates. Returns the date field or the earliest date
    possible in Python. With this done, items without dates will be listed
    last without throwing errors to the sort function."""
    if (doc.dateFiled != None):
        return doc.dateFiled
    else:
        import datetime
        return datetime.date(1, 1, 1)

def make_date_query(cd, request):
    '''Given the cleaned data from a form, return a valid Solr fq string'''
    before = cd['filed_before']
    after = cd['filed_after']

    try:
        if after > before:
            message = 'You\'ve requested all documents before %s and after\
                       %s. Since %s comes before %s, these filters cannot not be \
                       used' % (before.date(),
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

def show_results(request):
    solr_log = open('/var/log/solr/solr.log', 'a')
    solr_log.write('\n\n')
    solr_log.close()
    print
    print
    print "Running the show_results view..."
    '''Show the results for a query
    
    Implements a parallel faceted search interface with Solr as the backend.
    '''

    query = request.GET.get('q', '*')


    # this handles the alert creation form.
    if request.method == 'POST':
        # an alert has been created
        alert_form = CreateAlertForm(request.POST)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the alert
            a = CreateAlertForm(cd)
            alert = a.save()

            # associate the user with the alert
            up = request.user.get_profile()
            up.alert.add(alert)
            messages.add_message(request, messages.SUCCESS,
                                 'Your alert was created successfully.')

            # and redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')
    else:
        # the form is loading for the first time, load it, then load the rest
        # of the page
        alert_form = CreateAlertForm(initial={'alertText': query,
                                              'alertFrequency': "dly"})

    '''
    Code beyond this point will be run if the alert form failed, or if the 
    submission was a GET request. Beyond this point, we run the searches.
    '''
    search_form = SearchForm(request.GET)

    main_params = {}
    court_facet_params = {}
    stat_facet_params = {}
    if search_form.is_valid():
        cd = search_form.cleaned_data

        # Build up all the queries needed
        main_params['q'] = cd['q']
        court_facet_params['q'] = cd['q']
        stat_facet_params['q'] = cd['q']

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
        # If there aren't any hits in the text return the field instead
        main_params['f.text.hl.alternateField'] = 'text'
        main_params['f.text.hl.maxAlternateFieldLength'] = '500'
        main_params['f.caseName.hl.alternateField'] = 'caseName'
        main_params['f.westCite.hl.alternateField'] = 'westCite'
        main_params['f.docketNumber.hl.alternateField'] = 'docketNumber'
        main_params['f.lexisCite.hl.alternateField'] = 'lexisCite'
        main_params['f.court_citation_string.hl.alternateField'] = 'court_citation_string'

        main_fq = []
        court_fq = []
        stat_fq = []
        # Case Name
        if cd['case_name'] != '':
            main_fq.append('caseName:' + cd['case_name'])
            court_fq.append('caseName:' + cd['case_name'])
            stat_fq.append('caseName:' + cd['case_name'])

        # Citations
        if cd['west_cite'] != '':
            main_fq.append('westCite:' + cd['west_cite'])
            court_fq.append('westCite:' + cd['west_cite'])
            stat_fq.append('westCite:' + cd['west_cite'])
        if cd['docket_number'] != '':
            main_fq.append('docketNumber:' + cd['docket_number'])
            court_fq.append('docketNumber:' + cd['docket_number'])
            stat_fq.append('docketNumber:' + cd['docket_number'])

        # Dates
        date_query = make_date_query(cd, request)
        main_fq.append(date_query)
        court_fq.append(date_query)
        stat_fq.append(date_query)

        # Faceting
        court_facet_params['rows'] = '0'
        stat_facet_params['rows'] = '0'
        court_facet_params['facet'] = 'true'
        stat_facet_params['facet'] = 'true'
        court_facet_params['facet.mincount'] = 0
        stat_facet_params['facet.mincount'] = 0
        court_facet_params['facet.field'] = '{!ex=dt}court_exact'
        stat_facet_params['facet.field'] = '{!ex=dt}status_exact'
        selected_courts = [k.replace('court_', '')
                           for k, v in cd.iteritems()
                           if (k.startswith('court_') and v == True)]
        selected_courts = ' OR '.join(selected_courts)
        selected_stats = [k.replace('stat_', '')
                          for k, v in cd.iteritems()
                          if (k.startswith('stat_') and v == True)]
        selected_stats = ' OR '.join(selected_stats)
        if len(selected_courts) > 0:
            court_fq.extend(['{!tag=dt}court_exact:(%s)' % selected_courts,
                             'status_exact:(%s)' % selected_stats])
        if len(selected_stats) > 0:
            stat_fq.extend(['{!tag=dt}status_exact:(%s)' % selected_stats,
                            'court_exact:(%s)' % selected_courts])
        if len(selected_courts) + len(selected_stats) > 0:
            main_fq.extend(['{!tag=dt}status_exact:(%s)' % selected_stats,
                            '{!tag=dt}court_exact:(%s)' % selected_courts])

        # If a param has been added to the fq variables, then we add them to the
        # main_params var. Otherwise, we don't, as doing so throws an error.
        if len(main_fq) > 0:
            main_params['fq'] = main_fq
        if len(court_fq) > 0:
            court_facet_params['fq'] = court_fq
        if len(stat_fq) > 0:
            stat_facet_params['fq'] = stat_fq

    else:
        print "The form is invalid or unbound."
        #TODO: Remove before sending live
        messages
        main_params['q'] = '*'

    # Run the query
    print "Params sent to search are: %s" % '&'.join(['%s=%s' % (k, v) for k, v in main_params.items()])
    results_si = conn.raw_query(**main_params)
    #print results_si.execute()
    try:
        results_si = conn.raw_query(**main_params)
        print results_si.execute()
        court_facet_fields = conn.raw_query(**court_facet_params).execute().facet_counts.facet_fields
        stat_facet_fields = conn.raw_query(**stat_facet_params).execute().facet_counts.facet_fields
    except:
        return render_to_response('search/search.html',
                                  {'error': True, 'query': query},
                                  RequestContext(request))



    # Merge the fields with the facet values and set up the form fields.
    # We need to handle two cases:
    #   1. The initial load of the page. For this we use the checked attr that 
    #      is set on the form if there isn't a sort order in the request.
    #   2. The load after form submission. For this, we use the field.value().
    # The other thing we're accomplishing here is to merge the fields from 
    # Django with the counts from Solr.
    court_facets = []
    court_list = dict(court_facet_fields['court_exact'])
    for field in search_form:
        try:
            count = court_list[field.html_name.replace('court_', '')]
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
        court_facets.append(facet)

    status_facets = []
    status_list = dict(stat_facet_fields['status_exact'])
    for field in search_form:
        try:
            count = status_list[field.html_name.replace('stat_', '')]
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
        status_facets.append(facet)

    # Finally, we make a copy of request.GET so it is mutable, and we make
    # some adjustments that we want to see in the rendered form.
    mutable_get = request.GET.copy()
    # Send the user the cleaned up query
    mutable_get['q'] = cd['q']
    # Always reset the radio box to refine
    mutable_get['refine'] = 'refine'
    search_form = SearchForm(mutable_get)

    # Set up pagination
    try:
        paginator = Paginator(results_si, 20)
        page = request.GET.get('page', 1)
        try:
            paged_results = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            paged_results = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            paged_results = paginator.page(paginator.num_pages)
        #print "alert.search.views facet_fields.facet_counts: %s" % facet_fields
    except:
        # Catches any Solr errors, and simply aborts.
        return render_to_response('search/search.html',
                                  {'error': True, 'query': query},
                                  RequestContext(request))

    return render_to_response(
                  'search/search.html',
                  {'search_form': search_form, 'alert_form': alert_form,
                   'results': paged_results, 'court_facets': court_facets,
                   'status_facets': status_facets, 'query': query},
                  RequestContext(request))

    #############
    # SCRAPS
    #############
    #highlight_si = conn.query()
    #highlight_si = highlight_si.query(highlight_si.Q({'q':'court -newell'}))

    '''
    q_frags = query.split()
    results_si = conn.query(q_frags[0])
    facet_si = conn.query(q_frags[0])
    highlight_si = conn.query(q_frags[0])
    for frag in q_frags[1:]:
        results_si = results_si.query(frag)
        facet_si = facet_si.query(frag)
        highlight_si = highlight_si.query(frag)
    '''

    # Set up highlighting
    #hl_results = highlight_si.highlight('text', snippets=5).highlight('status')\
    #    .highlight('caseName').highlight('westCite').highlight('docketNumber')\
    #    .highlight('lexisCite').execute()
    #import pprint
    #pprint.pprint(hl_results)

    '''
    results = []
    for result in results_si.execute():
        #type(result['id'])
        #results_si[result['id']]['highlighted_text'] = result.highlighting['text']
        #results_si[hl_results.highlighting['search.document.464']]['highlighted_text'] = 'foo'
        temp_dict = {}
        try:
            temp_dict['caseName'] = hl_results.highlighting[result['id']]['caseName'][0]
        except KeyError:
            temp_dict['caseName'] = result['caseName']
        try:
            temp_dict['text'] = hl_results.highlighting[result['id']]['text']
        except KeyError:
            # No highlighting in the text for this result. Just assign the 
            # default unhighlighted value
            temp_dict['text'] = result['text']

        results.append(temp_dict)
    '''

    '''
    Goal:
     [doc1: {caseName: 'foo', text: 'bar', status:'baz'}]
    '''

    '''
    for d in r:
        d['highlighted_name'] = r.highlighting[d['id']]['name']
    book_list = r
    '''


def tools_page(request):
    return render_to_response('tools.html', {}, RequestContext(request))

def browser_warning(request):
    return render_to_response('browser_warning.html', {}, RequestContext(request))
