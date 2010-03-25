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


from django.shortcuts import render_to_response, HttpResponseRedirect
from django.template import RequestContext
from alert.search.forms import SearchForm
from alert.alertSystem.models import Document
from django.core.paginator import Paginator, InvalidPage, EmptyPage

def home(request):
    """Show the homepage"""
    print request.GET
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

    query = request.GET['q']
    
    # very unsophisticated search technique. Slow, cludgy, and MySQL
    # intensive. But functional, kinda. Sphinx code WILL go here.
    results = Document.objects.filter(documentPlainText__icontains=query).order_by("-dateFiled")

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

    return render_to_response('search/results.html',
        {'results': results, 'queryType': queryType, 'query': query},
        RequestContext(request))



def contactSample(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # pull the email addresses out of the MANAGERS tuple
            i = 0
            emailAddys = []
            while i < len(settings.MANAGERS):
                emailAddys.append(settings.MANAGERS[i][1])
                i += 1

            # send the email to the MANAGERS
            send_mail(
                "Message from " + cd['name'] + " at CourtListener.com",
                cd['message'],
                cd.get('email', 'noreply@example.com'),
                emailAddys,)
            # we must redirect after success to avoid problems with people using the refresh button.
            return HttpResponseRedirect('/contact/thanks/')
    else:
        # the form is loading for the first time
        try:
            email_addy = request.user.email
            full_name = request.user.get_full_name()
            form = ContactForm(
                initial = {'name': full_name, 'email': email_addy})
        except:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm()

    return render_to_response('contact/contact_form.html', {'form': form}, RequestContext(request))


def viewDocumentListByCourtSample(request, court):
    """Show documents for a court, ten at a time"""
    from django.core.paginator import Paginator, InvalidPage, EmptyPage
    if court == "all":
        # we get all records, sorted by dateFiled.
        docs = Document.objects.order_by("-dateFiled")
        ct = "All courts"
    else:
        ct = Court.objects.get(courtUUID = court)
        docs = Document.objects.filter(court = ct).order_by("-dateFiled")

    # we will show ten docs/page
    paginator = Paginator(docs, 10)

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # If page request is out of range, deliver last page of results.
    try:
        documents = paginator.page(page)
    except (EmptyPage, InvalidPage):
        documents = paginator.page(paginator.num_pages)

    return render_to_response('view_documents_by_court.html', {'title': ct,
        "documents": documents}, RequestContext(request))
