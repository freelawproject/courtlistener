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
from alert.userHandling.models import FREQUENCY
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext, loader, Context
from django.core.mail import send_mail, EmailMultiAlternatives


import datetime, time, calendar
        
def emailer(request, rate):
    """This will load all the users each day/week/month, and send them emails."""
    notes = []
    DEBUG = True
    
    # remap the FREQUENCY variable from the model so the human keys relate back 
    # to the indices     
    rates = {}
    for r in FREQUENCY:
        rates[r[1].lower()] = r[0]
    RATE = rates[rate]

    # sphinx likes time in UnixTime format, which the below accomplishes. Sadly,
    # there doesn't appear to be an easier way to do this. The output can be 
    # tested in the shell with: date --date="2010-04-16" +%s
    today = datetime.date.today()
    unixTimeToday = int(time.mktime(today.timetuple()))
    unixTimesPastWeek = []
    unixTimesPastMonth = []
    i = 0
    while i < 7:
        unixTimesPastWeek.append(unixTimeToday - (86400 * i))
        i += 1
    i = 0
    while i < calendar.mdays[datetime.date.today().month]:
        unixTimesPastMonth.append(unixTimeToday - (86400 * i))
        i += 1

    EMAIL_SUBJECT = 'New hits for your alert at CourtListener.com'
    EMAIL_SENDER = 'no-reply@courtlistener.com'
    
    # query all users with alerts of the desired frequency
    # use the distinct method to only return one instance of each person.
    userProfiles = UserProfile.objects.filter(alert__alertFrequency = RATE).distinct()

    
    # for each user with a daily, weekly or monthly alert...
    for userProfile in userProfiles:
        #...get their alerts...
        alerts = userProfile.alert.filter(alertFrequency = RATE)
        
        hits = []
        # ...and iterate over their alerts.
        for alert in alerts:
            if RATE == 'dly':
                print alert.alertText
                # query the alert
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimeToday)
            elif RATE == 'wly' and today.weekday() == 6:
                # if it's a weekly alert and today is Sunday
                print alert.alertText
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimesPastWeek)
            elif RATE == 'mly' and today.day == 1:
                # if it's a monthly alert and today is the first of the month
                print alert.alertText
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimesPastMonth)                
            elif RATE == "off":
                pass 
            
            
            # hits is a multidimensional array. Ugh.
            # it consists of alerts, paired with a list of documents, of the form:
            # [[alert1, [hit1, hit2, hit3, hit4]], [alert2, [hit1, hit2]]]
            if results.count() > 0:
                alertWithResults = [alert, results]
                hits.append(alertWithResults)
                
                # set the hit date to today
                alert.lastHitDate = datetime.date.today()
                alert.save()
                
            elif alert.sendNegativeAlert:
                # if they want an alert even when no hits.
                alertWithResults = [alert, "None"]
                hits.append(alertWithResults)

        
        if userProfile.plaintextPreferred:
            txtTemplate = loader.get_template('emails/email.txt')
            htmlTemplate = loader.get_template('emails/testing.html')
            c = Context({
                'hits': hits,
            })
            email_text = txtTemplate.render(c)
            html_text = htmlTemplate.render(c)
                        
            msg = EmailMultiAlternatives(EMAIL_SUBJECT, email_text, EMAIL_SENDER, [userProfile.user.email])
            msg.attach_alternative(html_text, "text/html")

            msg.send(fail_silently=False)


    return HttpResponse(notes)

def emailFoo(request):
    html = """<!DOCTYPE html>
<html>
    <head>
        <meta charset=utf-8>
        <title>CourtListener.com</title>
        <link rel="stylesheet" href="/media/css/blueprint/override.css" type="text/css" media="screen, projection">
        <link rel="stylesheet" href="/media/css/blueprint/screen.css" type="text/css" media="screen, projection">
        <link rel="stylesheet" href="/media/css/blueprint/plugins/fancy-type/screen.css" type="text/css" media="screen, projection">
    </head>
    <body>
        <h1 class="bottom"><a href="/">CourtListener</a></h1> 
        <h3 class="alt top bottom">(Beta)</h3>
        
        <hr>
        
        <h2>We have news regarding your alerts at <a href="/">CourtListener.com</a></h2>
        
            
                
                    
                    
                        <h3> class="alt bottom">Your weekly alert, "holder" had hits:</h3>
                    
                
                
                
                    <h3 class="alt bottom"><a href="/ca7/Francisca%20Paiz-Varga%20v.%20Eric%20Holder,%20Jr./">1. Francisca Paiz-Varga v. Eric Holder, Jr., 09-3369 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=showbr&amp;shofile=09-3369_001.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Francisca_Paiz-Varga_v._Eric_Holder_Jr..pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Eneh%20v.%20Holder/">2. Eneh v. Holder, 08-30322 ()</a></h3>
                    <p><strong>Status:</strong> Published<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/opinions/2010/04/15/05-75264.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Eneh_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Joseph%20v.%20Holder/">3. Joseph v. Holder, 07-56672 ()</a></h3>
                    <p><strong>Status:</strong> Published<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/opinions/2010/04/14/05-74390.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Joseph_v._Holder.pdf">>From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Lopez-jacuinde%20v.%20Holder/">4. Lopez-jacuinde v. Holder, 05-73609 ()</a></h3>
                    <p><strong>Status:</strong> Published<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/opinions/2010/04/12/07-72046.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Lopez-jacuinde_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Alsoofi%20v.%20Holder/">5. Alsoofi v. Holder, 06-73204 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/06-73204.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Alsoofi_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Harutyunyan%20v.%20Holder/">6. Harutyunyan v. Holder, 06-74594 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/06-74594.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Harutyunyan_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Stoliarova%20v.%20Holder/">7. Stoliarova v. Holder, 06-74688 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/06-74688.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Stoliarova_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Lin%20v.%20Holder/">8. Lin v. Holder, 06-75274 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/06-75274.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Lin_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Singh%20v.%20Holder/">9. Singh v. Holder, 06-75849 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/06-75849.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Singh_v._Holder.pdf">>From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Mkrtchyan%20v.%20Holder/">10. Mkrtchyan v. Holder, 07-70147 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-70147.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Mkrtchyan_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Cui%20v.%20Holder/">11. Cui v. Holder, 07-70399 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-70399.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Cui_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Ram%20v.%20Holder/">12. Ram v. Holder, 07-71978 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-71978.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Ram_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Prasad%20v.%20Holder/">13. Prasad v. Holder, 07-72294 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-72294.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Prasad_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Johal%20v.%20Holder/">14. Johal v. Holder, 07-72357 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-72357.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Johal_v._Holder.pdf">>From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Gurpreet%20Singh%20v.%20Holder/">15. Gurpreet Singh v. Holder, 07-72539 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-72539.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Gurpreet_Singh_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Ledezma%20v.%20Holder/">16. Ledezma v. Holder, 07-72740 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-72740.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Ledezma_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Ramirez-leon%20v.%20Holder/">17. Ramirez-leon v. Holder, 07-72765 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-72765.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Ramirez-leon_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Chavez-villegas%20v.%20Holder/">18. Chavez-villegas v. Holder, 07-73243 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-73243.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Chavez-villegas_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Alvarez-medina%20v.%20Holder/">19. Alvarez-medina v. Holder, 07-73270 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-73270.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Alvarez-medina_v._Holder.pdf">From our backup</a></p><br>

                
            
                
                
                
                    <h3 class="alt bottom"><a href="/ca9/Bal%20v.%20Holder/">20. Bal v. Holder, 07-73422 ()</a></h3>
                    <p><strong>Status:</strong> Unpublished<br>
                    <strong>Download pdf:</strong> <a href="http://www.ca9.uscourts.gov/datastore/memoranda/2010/04/16/07-73422.pdf">From the court</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="pdf/2010/04/16/Bal_v._Holder.pdf">From our backup</a></p><br>

                
            
        
        <p>Humbly,</p>
        <p>The bots at CourtListener.com</p>

        <p>P.S. If you should wish to turn off or adjust this alert, sign in and edit your alerts.</p>
    </body>
</html>"""
    
    return HttpResponse(html)
