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


from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from alert.contact.forms import ContactForm
from alert import settings

def contact(request):
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
            return HttpResponseRedirect('/contact/thanks/')
    else:
        form = ContactForm()
    return render_to_response('contact/contact_form.html', {'form': form})


def thanks(request):
    return render_to_response('contact/contact_thanks.html')

