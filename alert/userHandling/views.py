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
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect
import datetime
import random
import hashlib


@login_required
def viewAlerts(request):
    return render_to_response('profile/alerts.html', {},
        RequestContext(request))


@login_required
def viewSettings(request):
    oldEmail = request.user.email # this line has to be at the top to work.
    user = request.user
    up = user.get_profile()
    userForm = UserForm(request.POST or None, instance=user)
    profileForm = ProfileForm(request.POST or None, instance=up)
    if profileForm.is_valid() and userForm.is_valid():
        cd = userForm.cleaned_data
        newEmail = cd['email']

        if oldEmail != newEmail:
            # Email was changed.

            # Build the activation key for the new account
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activationKey = hashlib.sha1(salt+user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime.timedelta(5)

            # Toggle the confirmation status.
            up.emailConfirmed = False
            up.activationKey = activationKey
            up.key_expires = key_expires

            # Send the email.
            current_site = Site.objects.get_current()
            email_subject = 'Email changed successfully on ' + \
                current_site.name,
            email_body = "Hello, %s,\n\nYou have successfully changed your \
email address at %s. Please confirm this change by clicking the following \
link within 5 days:\n\nhttp://courtlistener.com/email/confirm/%s\n\n\
Thanks for using our site,\n\n\The CourtListener team\n\n\
-------------------\nFor questions or comments, please see our contact page, \
http://courtlistener.com/contact/." % (
                user.username,
                current_site.name,
                up.activationKey)
            send_mail(email_subject,
                      email_body,
                      'no-reply@courtlistener.com',
                      [newEmail])


        # New email address and changes above are saved here.
        profileForm.save()
        userForm.save()
        messages.add_message(request, messages.SUCCESS,
            'Your settings were saved successfully.')
        return HttpResponseRedirect('/profile/settings/')
    return render_to_response('profile/settings.html',
        {'profileForm': profileForm,
         'userForm': userForm}, RequestContext(request))


@login_required
def deleteProfile(request):
    if request.method == 'POST':
        # Gather their foreign keys, delete those, then delete their profile
        # and user info
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

    return render_to_response('profile/delete.html', {},
        RequestContext(request))


def deleteProfileDone(request):
    return render_to_response('profile/deleted.html', {},
        RequestContext(request))


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
        if request.method == 'POST':
            form = UserCreationFormExtended(request.POST)
            if form.is_valid():
                # it seems like I should use this, but it's causing trouble...
                cd = form.cleaned_data

                username = cd['username']
                password = cd['password1']
                email = cd['email']
                fname = cd['first_name']
                lname = cd['last_name']

                # make a new user that is active, but has not confirmed their
                # email.
                new_user = User.objects.create_user(username, email, password)
                new_user.first_name = fname
                new_user.last_name = lname
                new_user.save()

                # Build the activation key for the new account
                salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
                activationKey = hashlib.sha1(salt+new_user.username)\
                    .hexdigest()
                key_expires = datetime.datetime.today() + datetime\
                    .timedelta(5)

                # associate a new UserProfile associated with the new user
                # this makes it so every time we call get_profile(), we can be
                # sure there is a profile waiting for us (a good thing).
                up = UserProfile(user = new_user,
                                 activationKey = activationKey,
                                 key_expires = key_expires)
                up.save()

                # Log the user in (pulled from the login view and here:
                # http://bitbucket.org/ubernostrum/django-registration/src/\
                #   tip registration/backends/simple/__init__.py#cl-26
                new_user = authenticate(username=username, password=password)
                login(request, new_user)

                # Send an email with the confirmation link
                current_site = Site.objects.get_current()
                email_subject = 'Confirm your account on' + current_site.name,
                email_body = "Hello, %s, and thanks for signing up for an \
account!\n\nTo send you emails, we need you to activate your account with \
CourtListener.com. To activate your account, click this link within 5 days:\
\n\nhttp://courtlistener.com/email/confirm/%s\n\nThanks for using our site,\
\n\n\The CourtListener team\n\n\
-------------------\n\
For questions or comments, please see our contact page, \
http://courtlistener.com/contact/." % (
                    new_user.username,
                    up.activationKey)
                send_mail(email_subject,
                          email_body,
                          'no-reply@courtlistener.com',
                          [new_user.email])

                return HttpResponseRedirect('/register/success/?next=' \
                    + redirect_to)
        else:
            form = UserCreationFormExtended()
        return render_to_response("profile/register.html", {'form': form},
            RequestContext(request))
    else:
        # the user is already logged in, direct them to their settings page as
        # a logical fallback
        return HttpResponseRedirect('/profile/settings/')


def registerSuccess(request):
    '''all redirect security checks should be done by now. Inform the user of
    their status, and redirect them.'''
    redirect_to = request.REQUEST.get('next', '')
    return render_to_response('registration/registration_complete.html',
        {'redirect_to': redirect_to})


def combined_signin_register(request):
    """Checks that the user is anonymous, then allows them to register or
    sign-in"""
    if request.user.is_anonymous():
        next = request.REQUEST.get('next', '')
        form = UserCreationFormExtended()
        return render_to_response('profile/login_or_register.html',
            {'form': form, 'next': next}, RequestContext(request))
    else:
        return HttpResponseRedirect('/profile/settings/')


def confirmEmail(request, activationKey):
    """Checks if the confirmation link is valid. All code paths verified.
    mlissner, 2010-07-22"""
    try:
        user_profile = UserProfile.objects.get(activationKey=activationKey)
        if user_profile.emailConfirmed:
            # their email is already confirmed.
            return render_to_response('registration/confirm.html',
                {'alreadyConfirmed': True})
    except:
        return render_to_response('registration/confirm.html',
            {'invalid': True})
    if user_profile.key_expires < datetime.datetime.today():
        return render_to_response('registration/confirm.html',
            {'expired': True})
    user_profile.emailConfirmed = True
    user_profile.save()
    return render_to_response('registration/confirm.html', {'success': True})


def requestEmailConfirmation(request):
    if request.method == 'POST':
        # Send a new confirmation key to the email address provided.
        form = EmailConfirmationForm(request.POST)
        if form.is_valid():
            # we look up the user in the user table. If we find them, we send
            # an email, and associate the new confirmation link with that
            # account. If we don't find the user, we tell the person, and
            # point them towards the registration and forgot password pages.
            cd = form.cleaned_data
            email = cd['email']

            try:
                user = User.objects.get(email=email)
            except:
                return render_to_response(
                    'registration/request_email_confirmation.html',
                    {'unknownAccount': True, 'form': form},
                    RequestContext(request))

            # make a new activation key.
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activationKey = hashlib.sha1(salt+user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime.timedelta(5)

            # associate it with the user's account.
            up = user.get_profile()
            up.activationKey = activationKey
            up.key_expires = key_expires
            up.save()

            # and send the email
            current_site = Site.objects.get_current()
            email_subject = 'Confirm your account on' + current_site.name,
            email_body = "Hello, %s,\n\nPlease confirm your email address by \
clicking the following link within 5 days:\
\n\nhttp://courtlistener.com/email/confirm/%s\n\nThanks for using our site,\
\n\n\The CourtListener team\n\n\-------------------\n\
For questions or comments, please see our contact page, \
http://courtlistener.com/contact/." % (
                user.username,
                up.activationKey)
            send_mail(email_subject,
                      email_body,
                      'no-reply@courtlistener.com',
                      [user.email])

        return HttpResponseRedirect('/email-confirmation/success/')

    else:
        if request.user.is_anonymous():
            form = EmailConfirmationForm()
        else:
            up = UserProfile(user = request.user)
            if up.emailConfirmed:
                # their email is already confirmed.
                return render_to_response(
                    'registration/request_email_confirmation.html',
                    {'alreadyConfirmed': True}, RequestContext(request))
            else:
                # they are seeing the form for the first time, and their email
                # is unconfirmed.
                email_addy = request.user.email
                form = EmailConfirmationForm(initial = {'email': email_addy})
        return render_to_response(
            'registration/request_email_confirmation.html', {'form': form},
            RequestContext(request))


def emailConfirmSuccess(request):
    return render_to_response(
        'registration/request_email_confirmation_success.html',
        {}, RequestContext(request))


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
