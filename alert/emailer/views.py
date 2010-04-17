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
from django.template import RequestContext
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
    if DEBUG: notes.append("unixTimeToday: " + str(unixTimeToday))

    # for each user with a daily, weekly or monthly alert...
    for user in users:
        if DEBUG: notes.append("We entered the forloop\n")
        #...get their alerts...
        alerts = user.alert.filter(alertFrequency = rate)
        
        alertList = []
        for alert in alerts:
            alertList.append(alert.alertText) 
        
        
        
        # ...and iterate over their alerts.
        for alert in alerts:
            
            if rate == 'dly':
                if DEBUG: notes.append("User " + str(user) + " has the following alerts: " + str(alert) + "\n")
                
                # query the alert
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")
                if DEBUG: notes.append("results before filtering: " + str(results._sphinx))
                results = queryset.filter(datefiled=unixTimeToday)
                
                if DEBUG: notes.append("result: " + str(results._sphinx))
        
        print str(notes)
                
        return render_to_response('emails/testing.html',
            {'results': results, 'queryType': "search"},
            RequestContext(request))
#                if DEBUG:
#                    print results.count()
        """if hits:
            # append the correct data to the variables that will be handed
            # off to the email template
            pass
        else:
            # no hits, so punt to next alert
            pass"""
        
        # At this point, all alerts should have been run, and all hits found
        # so we send the email using django's sendmail function.
        # sendmail (blah, blah, something, something.)
    
    
    # finally, we're done, so we say so. Better output here would be good.        
    return HttpResponse(notes)
