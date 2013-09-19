from django.contrib.auth.models import User
from alert import settings
from alert.userHandling.forms import ProfileForm, UserForm, UserCreationFormExtended, EmailConfirmationForm
from alert.honeypot.decorators import check_honeypot

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.shortcuts import redirect
from django.template import RequestContext
from django.views.decorators.cache import never_cache

import datetime
import hashlib
import random
import re
from alert.userHandling.models import UserProfile


def redirect_to_settings(request):
    return redirect(view_settings, permanent=True)


@login_required
@never_cache
def view_alerts(request):
    return render_to_response('profile/alerts.html',
                              {'private': True},
                              RequestContext(request))


@login_required
@never_cache
def view_favorites(request):
    return render_to_response('profile/favorites.html', {'private': True},
                              RequestContext(request))


@login_required
@never_cache
def view_settings(request):
    old_email = request.user.email  # this line has to be at the top to work.
    user = request.user
    up = user.get_profile()
    user_form = UserForm(request.POST or None, instance=user)
    profile_form = ProfileForm(request.POST or None, instance=up)
    if profile_form.is_valid() and user_form.is_valid():
        cd = user_form.cleaned_data
        new_email = cd['email']

        if old_email != new_email:
            # Email was changed.

            # Build the activation key for the new account
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activation_key = hashlib.sha1(salt + user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime.timedelta(5)

            # Toggle the confirmation status.
            up.email_confirmed = False
            up.activation_key = activation_key
            up.key_expires = key_expires

            # Send the email.
            current_site = Site.objects.get_current()
            email_subject = 'Email changed successfully on ' + \
                            str(current_site.name)
            email_body = "Hello, %s,\n\nYou have successfully changed your \
email address at %s. Please confirm this change by clicking the following \
link within 5 days:\n\nhttp://courtlistener.com/email/confirm/%s\n\n\
Thanks for using our site,\n\nThe CourtListener team\n\n\
-------------------\nFor questions or comments, please see our contact page, \
http://courtlistener.com/contact/." % (
                user.username,
                current_site.name,
                up.activation_key)
            send_mail(email_subject,
                      email_body,
                      'CourtListener <noreply@courtlistener.com>',
                      [new_email])

            messages.add_message(request, messages.SUCCESS,
                                 'Your settings were saved successfully. To continue ' +
                                 'receiving emails, please confirm your new email address ' +
                                 'by checking your email within five days.')
        elif not up.email_confirmed:
            # they didn't just change their email, but it isn't confirmed.
            messages.add_message(request, messages.INFO,
                                 'Your email address has not been confirmed. To receive ' +
                                 'alerts, you must <a href="/email-confirmation/request/">' +
                                 'confirm your email address</a>.')
        else:
            # if the email wasn't changed, simply inform of success.
            messages.add_message(request, messages.SUCCESS,
                                 'Your settings were saved successfully.')

        # New email address and changes above are saved here.
        profile_form.save()
        user_form.save()

        return HttpResponseRedirect('/profile/settings/')
    return render_to_response('profile/settings.html',
                              {'profile_form': profile_form,
                               'user_form': user_form,
                               'private': True},
                              RequestContext(request))


@login_required
def deleteProfile(request):
    if request.method == 'POST':
        # Gather their foreign keys, delete those, then delete their profile
        # and user info
        try:
            # they may not have a userProfile (old bug)
            userProfile = request.user.get_profile()

            alerts = userProfile.alert.all()
            for alert in alerts:
                alert.delete()

            faves = userProfile.favorite.all()
            for fave in faves:
                fave.delete()

            userProfile.delete()
        except:
            pass

        request.user.delete()
        return HttpResponseRedirect('/profile/delete/done/')

    return render_to_response('profile/delete.html',
                              {'private': True},
                              RequestContext(request))


def deleteProfileDone(request):
    return render_to_response('profile/deleted.html',
                              {'private': True},
                              RequestContext(request))


@check_honeypot(field_name='skip_me_if_alive')
@never_cache
def register(request):
    """allow only an anonymous user to register"""
    redirect_to = request.REQUEST.get('next', '')
    if 'sign-in' in redirect_to:
        # thus, we don't redirect people back to the sign-in form
        redirect_to = ''

    # security checks:
    # Light security check -- make sure redirect_to isn't garbage.
    if not redirect_to or ' ' in redirect_to:
        redirect_to = settings.LOGIN_REDIRECT_URL

    # Heavier security check -- redirects to http://example.com should
    # not be allowed, but things like /view/?param=http://example.com
    # should be allowed. This regex checks if there is a '//' *before* a
    # question mark.
    elif '//' in redirect_to and re.match(r'[^\?]*//', redirect_to):
        redirect_to = settings.LOGIN_REDIRECT_URL

    if request.user.is_anonymous():
        if request.method == 'POST':
            try:
                stub_account = User.objects.filter(userprofile__stub_account=True).\
                                            get(email__iexact=request.POST.get('email'))
            except User.DoesNotExist:
                stub_account = False

            if not stub_account:
                form = UserCreationFormExtended(request.POST)
            else:
                form = UserCreationFormExtended(request.POST, instance=stub_account)

            if form.is_valid():
                cd = form.cleaned_data
                if not stub_account:
                    # make a new user that is active, but has not confirmed their email address
                    user = User.objects.create_user(cd['username'], cd['email'], cd['password1'])
                    up = UserProfile(user=user)
                else:
                    user = stub_account
                    user.set_password(cd['password1'])
                    up = stub_account.get_profile()
                    up.stub_account = False

                if cd['first_name']:
                    user.first_name = cd['first_name']
                if cd['last_name']:
                    user.last_name = cd['last_name']
                user.save()

                # Build and assign the activation key
                salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
                activation_key = hashlib.sha1(salt + user.username).hexdigest()
                key_expires = datetime.datetime.today() + datetime.timedelta(5)
                up.activation_key = activation_key
                up.key_expires = key_expires
                up.save()

                # Send an email with the confirmation link
                email_subject = 'Confirm your account on CourtListener.com'
                email_body = "Hello, %s, and thanks for signing up for an \
account!\n\nTo send you emails, we need you to activate your account with \
CourtListener.com. To activate your account, click this link within five days:\
\n\nhttps://www.courtlistener.com/email/confirm/%s\n\nThanks for using our site,\
\n\nThe CourtListener Team\n\n\
-------------------\n\
For questions or comments, please see our contact page, \
https://www.courtlistener.com/contact/." % (user.username, up.activation_key)
                send_mail(
                    email_subject,
                    email_body, 'CourtListener <noreply@courtlistener.com>',
                    [user.email]
                )
                return HttpResponseRedirect('/register/success/?next=%s' % redirect_to)
        else:
            form = UserCreationFormExtended()
        return render_to_response("profile/register.html",
                                  {'form': form, 'private': False},
                                  RequestContext(request))
    else:
        # The user is already logged in. Direct them to their settings page as
        # a logical fallback
        return HttpResponseRedirect('/profile/settings/')


@never_cache
def register_success(request):
    """Tell the user they have been registered and allow them to continue where they left off."""
    redirect_to = request.REQUEST.get('next', '')
    return render_to_response('registration/registration_complete.html',
                              {'redirect_to': redirect_to, 'private': True},
                              RequestContext(request))


@never_cache
def confirmEmail(request, activation_key):
    """Confirms email addresses for a user and sends an email to the admins.

    Checks if a hash in a confirmation link is valid, and if so validates the
    user's email address as valid.
    """
    try:
        user_profile = UserProfile.objects.get(activation_key=activation_key)
    except UserProfile.DoesNotExist:
        return render_to_response('registration/confirm.html',
                                  {'invalid': True, 'private': True},
                                  RequestContext(request))

    if user_profile.email_confirmed:
        # their email is already confirmed.
        return render_to_response('registration/confirm.html',
                                  {'alreadyConfirmed': True, 'private': True},
                                  RequestContext(request))

    if user_profile.key_expires < datetime.datetime.today():
        return render_to_response('registration/confirm.html',
                                  {'expired': True, 'private': True},
                                  RequestContext(request))

    # Tests pass; Save the profile
    user_profile.email_confirmed = True
    user_profile.save()

    # Send an email letting the admins know there's somebody to say hi to
    email_subject = 'New user confirmed on CourtListener: %s' % user_profile.user.username
    email_body = ("A new user has signed up on CourtListener! Maybe we should say hi?\n\n"
                 "Their name is: %s\n"
                 "Their email address is: %s\n\n"
                 "Sincerely,\n\n"
                 "The CourtListener Bots" % (user_profile.user.get_full_name() or "Not provided",
                                             user_profile.user.email))
    send_mail(email_subject,
              email_body,
              'CourtListener <noreply@courtlistener.com>',
              [a[1] for a in settings.ADMINS])

    return render_to_response('registration/confirm.html',
                              {'success': True, 'private': True},
                              RequestContext(request))


@check_honeypot(field_name='skip_me_if_alive')
def request_email_confirmation(request):
    """Send an email confirmation email"""
    if request.method == 'POST':
        form = EmailConfirmationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                user = User.objects.get(email__iexact=cd['email'])
                up = user.get_profile()
            except User.DoesNotExist:
                # Normally, we'd throw an error here, but we don't want to reveal what accounts we have on file, so
                # instead, we just pretend like it worked.
                return HttpResponseRedirect('/email-confirmation/success/')

            # make a new activation key.
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activation_key = hashlib.sha1(salt + user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime.timedelta(5)

            # associate it with the user's account.
            up.activation_key = activation_key
            up.key_expires = key_expires
            up.save()

            email_subject = 'Confirm your account on CourtListener.com'
            email_body = ("Hello %s,\n\n"
                          "Somebody, probably you, has asked that we send an email confirmation link to this address.\n\n"
                          "If this was you, please confirm your email address by clicking the following link within "
                          "five days:\n\n"
                          "https://www.courtlistener.com/email/confirm/%s\n\n"
                          "If this was not you, please disregard this email.\n\n"
                          "Thanks for using our site,\n"
                          "The CourtListener Team\n\n"
                          "-------\n"
                          "For questions or comments, please visit our contact page, "
                          "https://www.courtlistener.com/contact/\n"
                          "We're always happy to hear from you." % (user.username, up.activation_key))
            send_mail(email_subject,
                      email_body,
                      'CourtListener <noreply@courtlistener.com>'
                      [user.email])
            return HttpResponseRedirect('/email-confirmation/success/')
    else:
        form = EmailConfirmationForm()
    return render_to_response('registration/request_email_confirmation.html',
                              {'private': True, 'form': form},
                              RequestContext(request))


@never_cache
def emailConfirmSuccess(request):
    return render_to_response('registration/request_email_confirmation_success.html',
                              {'private': False},
                              RequestContext(request))


@login_required
@never_cache
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
    return render_to_response('profile/password_form.html',
                              {'form': form, 'private': False},
                              RequestContext(request))
