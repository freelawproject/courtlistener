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

from alert.userHandling.models import Alert, UserProfile
from alert.alertSystem.models import Document
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext, loader, Context
from alert.userHandling.models import FREQUENCY


import datetime, time
        
def emailer(request, rate):
    """This will load all the users each day/week/month, and send them emails."""
    notes = []
    DEBUG = True
    
    # remap the FREQUENCY variable from the model so the human keys relate back 
    # to the indices     
    rates = {}
    for r in FREQUENCY:
        rates[r[1].lower()] = r[0]
    rate = rates[rate]

    # query all users with alerts of the desired frequency
    # use the distinct method to only return one instance of each person.
    users = UserProfile.objects.filter(alert__alertFrequency = rate).distinct()
    
    # sphinx likes time in UnixTime format, which the below accomplishes. Sadly,
    # there doesn't appear to be an easier way to do this. The output can be 
    # tested in the shell with: date --date="2010-04-16" +%s
    unixTimeToday = int(time.mktime(datetime.date.today().timetuple()))

    # for each user with a daily, weekly or monthly alert...
    for user in users:
        #...get their alerts...
        alerts = user.alert.filter(alertFrequency = rate)
        
        hits = []
        # ...and iterate over their alerts.
        for alert in alerts:
            if rate == 'dly':
                print alert.alertText
                # query the alert
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimeToday)

                if DEBUG: notes.append("result: " + str(results._sphinx) + "<br>")
                
                # hits is a multidimensional array. Ugh.
                # it consists of alerts, paired with a list of documents, of the form:
                # [[alert1, [hit1, hit2, hit3, hit4]], [alert2, [hit1, hit2]]]
                if results.count() > 0:
                    alertWithResults = [alert, results]
                    hits.append(alertWithResults)
        
                
        
        if user.plaintextPreferred:
            hits
            t = loader.get_template('emails/email.txt')
            c = Context({
                'hits': hits,
            })
            
            print t.render(c)

            """
            send_mail('New hits for your alert at CourtListener.com', 
                t.render(c), 'no-reply@courtlistener.com', [user.email], 
                fail_silently=False)
        elif not user.plaintextPreferred:
            send_mail('New hits for your alert at CourtListener.com', 
                t.render(c), 'no-reply@courtlistener.com', [user.email], 
                fail_silently=False)
            """
    return HttpResponse(notes)
