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
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
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
            up = request.user.get_profile()
            profileForm = ProfileForm(request.POST, instance = up)
            profileForm.save()
            
            #change things to the user
            cd = userForm.cleaned_data
            userForm = UserForm(cd, instance = request.user)
            userForm.save()
            messages.add_message(request, messages.SUCCESS, 
                'Your settings were saved successfully.')
            return HttpResponseRedirect('/profile/settings/')
        
    else:
        # the form is loading for the first time
        userForm = UserForm(instance = request.user)
        
        try:
            userProfile = request.user.get_profile()
            profileForm = ProfileForm(instance = userProfile)
        except:
            # if no userProfile exists yet (cause the user hasn't created one) do this
            profileForm = ProfileForm(instance = request.user)


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
    
def register(request):
    """allow an anonymous user to register"""
    from django.contrib.auth.forms import UserCreationForm
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            
            # make a new user, and then a new UserProfile associated with it.
            # this makes it so every time we call get_profile(), we can be sure
            # there is a profile waiting for us (a good thing).
            new_user = form.save()
            up = UserProfile()
            up.user = new_user
            up.save()
            
            # make these into strings so we can pass them off to the template
            username = str(cd['username'])
            password = str(cd['password1'])
            
            return render_to_response("profile/register_success.html", 
                {'form': form, 'username': username, 'password': password}, 
                RequestContext(request))
            
    else:
        form = UserCreationForm()
    return render_to_response("profile/register.html", {'form': form}, 
        RequestContext(request))
        
def registerSuccess(request):
    return HttpResponseRedirect('/register/success')

@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, 
                'Your password was changed successfully.')
            return HttpResponseRedirect('/profile/password/change')
    else:
        form = PasswordChangeForm(user=request.user)
    return render_to_response('profile/password_form.html', {'form': form},
        RequestContext(request))
