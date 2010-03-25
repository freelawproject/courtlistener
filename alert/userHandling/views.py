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

from alert.userHandling.forms import *
from alert.userHandling.models import BarMembership
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect


@login_required
def viewAlerts(request):
    return render_to_response('profile/alerts.html', {}, 
        RequestContext(request))
   
@login_required    
def viewSettings(request):
    if request.method == 'POST':
        userForm = UserForm(request.POST)
        profileForm = ProfileForm(request.POST)
        if profileForm.is_valid() and userForm.is_valid():
            # Save things to the profile (this should be done with cleaned_data, 
            # but I can't get past an error with the barmemberships field...it's
            # strange and frustrating.
                
            # this is needed, since users won't have a userProfile at first
            try: 
                up = request.user.get_profile()
                profileForm = ProfileForm(request.POST, instance = up)
            except:
                # if they don't have a userProfile, we make them one, even if it's empty
                up = UserProfile()
                up.user = request.user
                profileForm = ProfileForm(request.POST, instance = up)
            profileForm.save()
            
          
            #change things to the user
            cd = userForm.cleaned_data
            userForm = UserForm(cd, instance = request.user)
            userForm.save()
            return HttpResponseRedirect('/profile/settings/')
        
    else:
        # the form is loading for the first time
        # first, we get the stuff from the user form
        user = request.user
        fname = user.first_name
        lname = user.last_name
        email = user.email
        userForm = UserForm(
            initial = {'first_name': fname, 'last_name':lname, 'email': email}
        )
        
        try:
            userProfile = request.user.get_profile()
            employer = userProfile.employer
            bar_memberships = userProfile.barmembership.all()
            location = userProfile.location
            plaintextPreferred = userProfile.plaintextPreferred
            wantsNewsletter = userProfile.wantsNewsletter
            profileForm = ProfileForm(
            initial = {'employer': employer, 'barmembership' : bar_memberships,
                'location': location, 'plaintextPreferred': plaintextPreferred,
                'wantsNewsletter': wantsNewsletter}
           )
        except:
            # if no userProfile exists yet (cause the user hasn't created one) do this
            profileForm = ProfileForm()


    return render_to_response('profile/settings.html', {'profileForm': profileForm, 
        'userForm': userForm}, RequestContext(request))


@login_required
def deleteProfile(request):
    if request.method == 'POST':
        # Gather their foreign keys, delete those, then delete their profile and user info
        try:
            # they may not have a userProfile
            userProfile = request.user.get_profile()    

            alerts = userProfile.alert.all()
            for alert in alerts:
                alert.delete()
                
            userProfile.delete()
        except:
            pass
        
        request.user.delete()
        
        return HttpResponseRedirect('/profile/delete/done')
    
    
    return render_to_response('profile/delete.html', {}, RequestContext(request))
        

def deleteProfileDone(request):
    return render_to_response('profile/deleted.html', {}, RequestContext(request))
