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
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.views import login as signIn
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect
import datetime, random, hashlib


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

        return HttpResponseRedirect('/profile/delete/done/')


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
                # it seems like I should use this, but it's causing trouble...
                cd = form.cleaned_data

                username = str(cd['username'])
                password = str(cd['password1'])
                email = str(cd['email'])
                fname = str(cd['first_name'])
                lname = str(cd['last_name'])

                # make a new user that is inactive
                new_user = User.objects.create_user(username, email, password)
                new_user.first_name = fname
                new_user.last_name = lname
                new_user.save()

                # Build the activation key for the new account
                salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
                activationKey = hashlib.sha1(salt+new_user.username).hexdigest()
                key_expires = datetime.datetime.today() + datetime.timedelta(5)

                # associate a new UserProfile associated with the new user
                # this makes it so every time we call get_profile(), we can be sure
                # there is a profile waiting for us (a good thing).
                up = UserProfile(user = new_user,
                                 activationKey = activationKey,
                                 key_expires = key_expires)
                up.save()

                # Send an email with the confirmation link
                current_site = Site.objects.get_current()
                email_subject = 'Confirm your account on' + current_site.name,
                email_body = "Hello, %s, and thanks for signing up for an \
account!\n\nTo send you emails, we need you to activate your account with CourtListener.com. \
To activate your account, click this link within 5 days:\
\n\nhttp://courtlistener.com/accounts/confirm/%s\n\nThanks for using our site,\n\n\
The CourtListener team\n\n\
-------------------\n\
For questions or comments, please see our contact page, http://courtlistener.com/contact/." % (
                    new_user.username,
                    up.activationKey)
                send_mail(email_subject,
                          email_body,
                          'no-reply@courtlistener.com',
                          [new_user.email])


#                # make these into strings so we can pass them off to the template
#                username = str(cd['username'])
#                password = str(cd['password1'])

                #return HttpResponseRedirect('/sign-in/?next=' + redirect_to)
                return render_to_response("registration/registration_complete.html",
                    {'email': new_user.email},
                    RequestContext(request))

        else:
            form = UserCreationFormExtended()
        return render_to_response("profile/register.html", {'form': form},
            RequestContext(request))
    else:
        # the user is already logged in, direct them to their settings page as a
        # logical fallback
        return HttpResponseRedirect('/profile/settings/')


def combined_signin_register(request):
    """This function uses the stock django sign-in function and the custom 
    register function to sign users in or register them, depending on what they
    try to do."""
    if request.user.is_anonymous():
        if request.method == 'POST':
            try:
                if request.POST['sign-in'] == "": 
                    # A user is signing in - run the signIn function.
                    return signIn(request)
            except:
                if request.POST['register'] == "": 
                    # A user is registering - run the register function
                    return register(request)
        else:
            form = UserCreationFormExtended()
            return render_to_response('profile/login_or_register.html', {'form': form},
                RequestContext(request))
    else:
        # the user is already logged in, direct them to their settings page as a
        # logical fallback
        return HttpResponseRedirect('/profile/settings/')


# I am half-convinced this method isn't being used at all, and that the corresponding
# url config is not either. Difficult to check, however. mlissner, 2010-07-20.
def registerSuccess(request):
    return HttpResponseRedirect('/register/success/')


@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS,
                'Your password was changed successfully.')
            return HttpResponseRedirect('/profile/password/change/')
    else:
        form = PasswordChangeForm(user=request.user)
    return render_to_response('profile/password_form.html', {'form': form},
        RequestContext(request))
