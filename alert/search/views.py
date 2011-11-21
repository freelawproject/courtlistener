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
from alert.search.forms import SearchForm
from alert.search.models import Document
from alert.userHandling.models import UserProfile

from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext
from django.utils.text import get_text_list
from haystack.views import SearchView
from haystack.forms import FacetedSearchForm


def message_user(query, request):
    '''Check that the user's query is valid in a number of ways:
      1. Are they using any invalid fields?
      2. ? 
    
    '''

    # TODO: Write the regexes to process this. Import from the search class 
    #       when doing so.

    if len(messageText) > 0:
        messages.add_message(request, messages.INFO, messageText)

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



class ParallelFacetedSearchView(SearchView):
    """Provides facet counts that do not change based on the results.
    
    In a parallel faceted search system, we do not show the counts for each 
    facet decreasing after we select one. If we do, we select facet 'foo', and 
    then facet 'baz' shows a count of zero (since when 'foo' is selected it has
    no results).
    """
    __name__ = 'ParallelFacetedSearchView'

    def __init__(self, *args, **kwargs):
        # Needed to switch out the default form class.
        if kwargs.get('form_class') is None:
            kwargs['form_class'] = FacetedSearchForm

        super(ParallelFacetedSearchView, self).__init__(*args, **kwargs)

    def build_form(self, form_kwargs=None):
        if form_kwargs is None:
            form_kwargs = {}

        # This way the form can always receive a list containing zero or more
        # facet expressions:
        form_kwargs['selected_facets'] = self.request.GET.getlist("selected_facets")

        return super(ParallelFacetedSearchView, self).build_form(form_kwargs)

    def extra_context(self):
        extra = super(ParallelFacetedSearchView, self).extra_context()
        extra['request'] = self.request
        extra['facets'] = self.form.search().facet_counts()
        extra['count'] = self.form.search().count()

        return extra



def show_results(request):
    '''Show the results for a query'''

    try:
        query = request.GET['q']
    except:
        # if somebody is URL hacking at /search/results/
        query = ""

    # this handles the alert creation form.
    if request.method == 'POST':
        from alert.userHandling.models import Alert
        # an alert has been created
        alertForm = CreateAlertForm(request.POST)
        if alertForm.is_valid():
            cd = alertForm.cleaned_data

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
        alertForm = CreateAlertForm(initial={'alertText': query, 'alertFrequency': "dly"})

    # alert the user if there are any errors in their query
    message_user(query, request)

    # adjust the query if need be for the search to happen correctly.
    query = adjust_query_for_user(query)

    # NEW SEARCH METHOD
    try:
        queryset = Document.search.query(internalQuery)
        results = queryset.set_options(mode="SPH_MATCH_EXTENDED2").order_by('-dateFiled')
    except:
        results = []

    # Put the results in order by dateFiled. Fixes issue 124
    # From: http://wiki.python.org/moin/HowTo/Sorting/
    # Need to do the [0:results.count()] business, else returns only first 20.
    # results = sorted(results[0:results.count()], key=getDateFiledOrReturnZero, reverse=True)

    # next, we paginate we will show ten results/page
    paginator = Paginator(results, 10)

    # this will fail when the search fails, so try/except is needed.
    try:
        numResults = paginator.count
    except:
        numResults = 0

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # only allow queries up to page 100.
    if page > 100:
        return render_to_response('search/results.html', {'over_limit': True,
            'query': query, 'alertForm': alertForm},
            RequestContext(request))

    # If page request is out of range, deliver last page of results.
    try:
        results = paginator.page(page)
    except (EmptyPage, InvalidPage):
        results = paginator.page(paginator.num_pages)
    except:
        results = []

    return render_to_response('search/results.html', {'results': results,
        'numResults': numResults, 'query': query, 'alertForm': alertForm},
        RequestContext(request))


def tools_page(request):
    return render_to_response('tools.html', {}, RequestContext(request))
