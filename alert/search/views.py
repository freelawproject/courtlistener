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
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.paginator import PageNotAnInteger
from django.core.paginator import EmptyPage
from django.conf import settings
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext

conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')


def message_user(query, request):
    '''Check that the user's query is valid in a number of ways:
      1. Are they using any invalid fields?
      2. ? 
    
    '''


    '''
    # TODO: Write the regexes to process this. Import from the search class 
    #       when doing so.

    if len(messageText) > 0:
        messages.add_message(request, messages.INFO, messageText)
    '''
    return True


def get_date_filed_or_return_zero(doc):
    """Used for sorting dates. Returns the date field or the earliest date
    possible in Python. With this done, items without dates will be listed
    last without throwing errors to the sort function."""
    if (doc.dateFiled != None):
        return doc.dateFiled
    else:
        import datetime
        return datetime.date(1, 1, 1)


def show_results(request):
    solr_log = open('/var/log/solr/solr.log', 'a')
    solr_log.write('\n\n')
    solr_log.close()
    print
    print
    '''Show the results for a query
    
    Implements a parallel faceted search interface with Solr as the backend.
    '''

    query = request.GET.get('q', '')

    # this handles the alert creation form.
    if request.method == 'POST':
        from alert.userHandling.models import Alert
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
        # of the page!
        alert_form = CreateAlertForm(initial={'alertText': query,
                                              'alertFrequency': "dly"})

    # alert the user if there are any errors in their query
    message_user(query, request)

    # Build up all the queries needed
    params = {}
    params['q'] = query
    params['facet'] = 'true'
    params['facet.field'] = ['status_exact', 'court_exact']
    #try:
    print "alert.search.views request.GET['selected_facets']: %s" % request.GET['selected_facets']
    params['selected_facets'] = request.GET['selected_facets']
    #except

    results_si = conn.raw_query(**params)
    facet_fields = results_si.execute().facet_counts.facet_fields

    # Set up pagination
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
    print "alert.search.views facet_fields.facet_counts: %s" % facet_fields

    return render_to_response('search/search.html', {'query': query,
                              'alert_form': alert_form, 'results': paged_results,
                              'facet_fields': facet_fields},
                              RequestContext(request))

    #############
    # SCRAPS
    #############
    #results_foo = results_si.execute()
    #print results_foo[0]['caseName']

    #                            &facet=true     facet.field=status_exact                      &q=court+-newell
    #                            &facet=true     facet.field=court_exact&facet.field=status_exact&q=court+-newell
    #facet_si = conn.raw_query(**{'facet':'true', 'facet.field':['court_exact', 'status_exact'], 'q':query}).execute()
    #print facet_si
    #facet_si = facet_si.facet_by('court_exact')
    #highlight_si = conn.query()
    #highlight_si = highlight_si.query(highlight_si.Q({'q':'court -newell'}))
    #INFO: [] webapp=/solr path=/select/ params={q=q} hits=35 status=0 QTime=1 

    #INFO: [] webapp=/solr path=/select/ params={q=court+-newell} hits=733 status=0 QTime=2 
    #INFO: [] webapp=/solr path=/select/ params={q=court\+\-newell} hits=0 status=0 QTime=1


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

    # Set up facet counts
    #facet_fields = {}
    #facet_fields = facet_si.facet_by('court_exact', mincount=1).facet_by('status_exact').execute().facet_counts.facet_fields

    # Set up highlighting
    #hl_results = highlight_si.highlight('text', snippets=5).highlight('status')\
    #    .highlight('caseName').highlight('westCite').highlight('docketNumber')\
    #    .highlight('lexisCite').highlight('westCite').execute()
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
