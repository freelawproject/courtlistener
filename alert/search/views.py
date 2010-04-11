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

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.shortcuts import render_to_response, HttpResponseRedirect
from django.template import RequestContext
from alert.search.forms import SearchForm, CreateAlertForm
from alert.alertSystem.models import Document
from alert.userHandling.models import Alert, UserProfile

def home(request):
    """Show the homepage"""
    if "q" in request.GET:
        # using get because that way users can email queries (a good thing)
        form = SearchForm(request.GET)
        if form.is_valid():
            cd = form.cleaned_data
            query = cd['q']

            try:
                if request.GET['search'] == "":
                    queryType = 'search'
                    return HttpResponseRedirect('/search/results/?q=' + query)
            except:
                if request.GET['alert'] == "":
                    queryType = 'alert'
                    return HttpResponseRedirect('/alert/preview/?q=' + query)

    else:
        # the form is loading for the first time
        form = SearchForm()

    return render_to_response('home_page.html', {'form': form},
        RequestContext(request))


def showResults(request, queryType):
    """Show the results for a query as either an alert or a search"""
    if queryType == "alert/preview":
        queryType = "alert"
    elif queryType == "search/results":
        queryType = "search"
    
    try:
        query = request.GET['q']
    except:
        # if somebody is URL hacking at /search/results/ or alert/preview/
        query = ""
#    
#    if '@docStatus precedential' in query or '@docStatus published' in query:
#        query = query.replace('@docStatus precedential', '@docStatus P')
#        query = query.replace('@docStatus published', '@docStatus P')
#        messages.add_message(request, messages.INFO,
#            'Your query has been changed to read @docStatus P')
#    if '@docStatus unpublished' in query or '@docStatus unprecedential' in query:
#        query = query.replace('@docStatus unpublished', '@docStatus U')
#        query = query.replace('@docStatus unprecedential', '@docStatus U')
#        messages.add_message(request, messages.INFO,
#            'Your query has been changed to read @docStatus U')

    # this handles the alert creation form.
    if request.method == 'POST':
        from alert.userHandling.models import Alert
        # an alert has been created
        alertForm = CreateAlertForm(request.POST)
        if alertForm.is_valid():
            cd = alertForm.cleaned_data

            # save the alert
            a = CreateAlertForm(cd)
            alert = a.save() # this method saves it and returns it

            # associate the user with the alert
            try:
                # This works...but only if they already have an account.
                up = request.user.get_profile()
            except:
                # if the user doesn't have a profile yet, we make them one, and
                # associate it with their username.
                u = request.user
                up = UserProfile()
                up.user = u
                up.save()
            up.alert.add(alert)
            messages.add_message(request, messages.SUCCESS,
                    'Your alert was created successfully.')

            # and redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')
    else:
        # the form is loading for the first time, load it, then load the rest
        # of the page!
        alertForm = CreateAlertForm(initial = {'alertText': query})

    # OLD SEARCH METHOD
    # results = Document.objects.filter(documentPlainText__icontains=query).order_by("-dateFiled")
    
    # Sphinx search
    """Known problems:
        - punctuation in a phrase search may break it.
        - length of phrase searches may be limited.
        - date fields don't work
        - error when doing @docStatus u
        - searching for tests and test yields different results."""
    try:
        queryset = Document.search.query(query)
        results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
            .order_by('-dateFiled')
    except:
        results = []

    # next, we paginate we will show ten results/page
    paginator = Paginator(results, 10)

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # If page request is out of range, deliver last page of results.
    try:
        results = paginator.page(page)
    except (EmptyPage, InvalidPage):
        results = paginator.page(paginator.num_pages)
    except:
        results = []

    return render_to_response('search/results.html',
        {'results': results, 'queryType': queryType, 'query': query,
        'alertForm': alertForm}, RequestContext(request))


@login_required
def editAlert(request, alertID):
    user = request.user.get_profile()

    try:
        alertID = int(alertID)
    except:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking...
    for alert in user.alert.all():
        if alertID == alert.alertUUID:
            # they can edit it
            canEdit = True
            # pull it from the DB
            alert = Alert.objects.get(alertUUID = alertID)
            break
        else:
            canEdit = False

    if canEdit == False:
        # we just send them home, they can continue playing
        return HttpResponseRedirect('/')

    elif canEdit:
        # they can edit the item, therefore, we load the form.
        if request.method == 'POST':
            form = CreateAlertForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data

                # save the changes
                a = CreateAlertForm(cd, instance=alert)
                a.save() # this method saves it and returns it
                messages.add_message(request, messages.SUCCESS,
                    'Your alert was saved successfully.')


                # redirect to the alerts page
                return HttpResponseRedirect('/profile/alerts/')

        else:
            # the form is loading for the first time
            form = CreateAlertForm(instance = alert)

        return render_to_response('profile/edit_alert.html', {'form': form, 'alertID': alertID}, RequestContext(request))


@login_required
def deleteAlert(request, alertID):
    user = request.user.get_profile()

    try:
        alertID = int(alertID)
    except:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking...
    for alert in user.alert.all():
        if alertID == alert.alertUUID:
            # they can edit it
            canEdit = True
            # pull it from the DB
            alert = Alert.objects.get(alertUUID = alertID)
            break
        else:
            canEdit = False

    if canEdit == False:
        # we send them home
        return HttpResponseRedirect('/')

    elif canEdit:
        # Then we delete it, and redirect them.
        alert.delete()
        messages.add_message(request, messages.SUCCESS,
            'Your alert was deleted successfully.')
        return HttpResponseRedirect('/profile/alerts/')
