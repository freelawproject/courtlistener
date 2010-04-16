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
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse

from alert.userHandling.models import FREQUENCY 


        
        
def emailer(request, rate):
    """This will load all the users each day/week/month, and send them emails."""
    # remap the FREQUENCY variable from the model so the human keys relate back 
    # to the indices     
    rates = {}
    for r in FREQUENCY:
        rates[r[1].lower()] = r[0]
    
    rate = rates['rate']
    
    
    """TODO: this and the next step can/should be done with a subquery using the __IN syntax.""" 
    
    
    
    # query all users with alerts of the desired frequency
    # use the distinct method to only return one instance of each person.
    users = UserProfile.objects.filter(alert__alertFrequency = rate).distinct()
    
    # for each user with a daily, weekly or monthly alert...
    for user in users:
        #...get their alerts...
        alerts = user.alert.filter(alertFrequency = rate)
        
        # ...and iterate over their alerts.
        for alert in alerts:
            print "User " + str(user) + " has the following alerts: " + str(alert)
            
            # query the alert (REPLACE THIS LINE WITH SPHINX CONFIG)
            hits = "Query the results"
            
            if hits:
                # append the correct data to the variables that will be handed
                # off to the email template
                pass
            else:
                # no hits, so punt to next alert
                pass
        
        # At this point, all alerts should have been run, and all hits found
        # so we send the email using django's sendmail function.
        # sendmail (blah, blah, something, something.)
    
    
    # finally, we're done, so we say so. Better output here would be good.        
    return HttpResponse("DONE")
