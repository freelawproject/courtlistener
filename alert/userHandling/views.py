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

from alert.settings import LOGIN_REDIRECT_URL
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
    userForm = UserForm(request.POST or None, instance=request.user)
    profileForm = ProfileForm(request.POST or None, instance=request.user.get_profile())
    if profileForm.is_valid() and userForm.is_valid():
        profileForm.save()
        userForm.save()
        messages.add_message(request, messages.SUCCESS, 
            'Your settings were saved successfully.')
        return HttpResponseRedirect('/profile/settings/')
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
    """allow only an anonymous user to register"""
    
    redirect_to = request.REQUEST.get('next', '')
    
    # security checks:
    # Light security check -- make sure redirect_to isn't garbage.
    if not redirect_to or ' ' in redirect_to:
        redirect_to = LOGIN_REDIRECT_URL
    
    # Heavier security check -- redirects to http://example.com should 
    # not be allowed, but things like /view/?param=http://example.com 
    # should be allowed. This regex checks if there is a '//' *before* a
    # question mark.
    elif '//' in redirect_to and re.match(r'[^\?]*//', redirect_to):
        redirect_to = settings.LOGIN_REDIRECT_URL
    
    if request.user.is_anonymous():
        from django.contrib.auth.forms import UserCreationForm
        if request.method == 'POST':
            form = UserCreationFormExtended(request.POST)
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
                
                return HttpResponseRedirect('/sign-in/?next=' + redirect_to)
                
        else:
            form = UserCreationFormExtended()
        return render_to_response("profile/register.html", {'form': form}, 
            RequestContext(request))
    else:
        # the user is already logged in, direct them to their settings page as a
        # logical fallback
        return HttpResponseRedirect('/profile/settings/')
        
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
