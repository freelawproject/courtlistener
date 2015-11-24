import hashlib
import logging
import random
import re
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import (sensitive_post_parameters,
                                           sensitive_variables)
from cl import settings
from cl.custom_filters.decorators import check_honeypot
from cl.favorites.forms import FavoriteForm
from cl.lib import search_utils
from cl.stats import tally_stat
from cl.users.forms import (
    ProfileForm, UserForm, UserCreationFormExtended, EmailConfirmationForm,
    CustomPasswordChangeForm
)
from cl.users.models import UserProfile
from cl.users.utils import convert_to_stub_account, emails, message_dict
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


@login_required
@never_cache
def view_alerts(request):
    alerts = request.user.alerts.all()
    for a in alerts:
        alert_dict = search_utils.get_string_to_dict(a.query)
        if alert_dict.get('type') == 'oa':
            a.type = 'oa'
        else:
            a.type = 'o'
    return render_to_response(
        'profile/alerts.html',
        {'alerts': alerts,
         'private': True},
        RequestContext(request)
    )


@login_required
@never_cache
def view_favorites(request):
    favorites = request.user.favorites.all().order_by('pk')
    favorite_forms = []
    for favorite in favorites:
        favorite_forms.append(FavoriteForm(instance=favorite))
    return render_to_response(
        'profile/favorites.html',
        {'private': True,
         'favorite_forms': favorite_forms,
         'blank_favorite_form': FavoriteForm()},
        RequestContext(request)
    )


@login_required
@never_cache
def view_donations(request):
    return render_to_response('profile/donations.html',
                              {'private': True},
                              RequestContext(request))


@permission_required('visualizations.has_beta_access')
@login_required
@never_cache
def view_visualizations(request):
    visualizations = SCOTUSMap.objects.filter(
        user=request.user,
        deleted=False
    ).order_by(
        '-date_modified',
    )
    return render_to_response(
        'profile/visualizations.html',
        {
            'visualizations': visualizations,
            'private': True,
        },
        RequestContext(request))


@permission_required('visualizations.has_beta_access')
@login_required
@never_cache
def view_deleted_visualizations(request):
    thirty_days_ago = now() - timedelta(days=30)
    visualizations = SCOTUSMap.objects.filter(
        user=request.user,
        deleted=True,
        date_deleted__gte=thirty_days_ago,
    ).order_by(
        '-date_modified',
    )
    return render_to_response(
        'profile/visualizations_deleted.html',
        {
            'visualizations': visualizations,
            'private': True,
        },
        RequestContext(request)
    )


@login_required
@never_cache
def view_api(request):
    return render_to_response('profile/api.html',
                              {'private': True},
                              RequestContext(request))


@sensitive_variables('salt', 'activation_key', 'email_body')
@login_required
@never_cache
def view_settings(request):
    old_email = request.user.email  # this line has to be at the top to work.
    user = request.user
    up = user.profile
    user_form = UserForm(request.POST or None, instance=user)
    profile_form = ProfileForm(request.POST or None, instance=up)
    if profile_form.is_valid() and user_form.is_valid():
        cd = user_form.cleaned_data
        new_email = cd['email']

        if old_email != new_email:
            # Email was changed.

            # Build the activation key for the new account
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            up.activation_key = hashlib.sha1(salt + user.username).hexdigest()
            up.key_expires = now() + timedelta(5)
            up.email_confirmed = False

            # Send the email.
            email = emails['email_changed_successfully']
            send_mail(
                email['subject'],
                email['body'] % (user.username, up.activation_key),
                email['from'],
                [new_email],
            )

            msg = message_dict['email_changed_successfully']
            messages.add_message(request, msg['level'], msg['message'])
            logout(request)
        else:
            # if the email wasn't changed, simply inform of success.
            msg = message_dict['settings_changed_successfully']
            messages.add_message(request, msg['level'], msg['message'])

        # New email address and changes above are saved here.
        profile_form.save()
        user_form.save()

        return HttpResponseRedirect(reverse('view_settings'))
    return render_to_response('profile/settings.html',
                              {'profile_form': profile_form,
                               'user_form': user_form,
                               'private': True},
                              RequestContext(request))


@login_required
def delete_account(request):
    if request.method == 'POST':
        try:
            request.user.alerts.all().delete()
            request.user.favorites.all().delete()
            convert_to_stub_account(request.user)
            email = emails['account_deleted']
            send_mail(email['subject'], email['body'] % request.user,
                      email['from'], email['to'])

        except Exception, e:
            logger.critical("User was unable to delete account. %s" % e)

        return HttpResponseRedirect('/profile/delete/done/')

    return render_to_response('profile/delete.html',
                              {'private': True},
                              RequestContext(request))


def delete_profile_done(request):
    return render_to_response('profile/deleted.html',
                              {'private': True},
                              RequestContext(request))


@sensitive_post_parameters('password1', 'password2')
@sensitive_variables('salt', 'activation_key', 'email_body')
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
                stub_account = User.objects.filter(
                    profile__stub_account=True,
                ).get(
                    email__iexact=request.POST.get('email'),
                )
            except User.DoesNotExist:
                stub_account = False

            if stub_account:
                form = UserCreationFormExtended(
                    request.POST,
                    instance=stub_account
                )
            else:
                form = UserCreationFormExtended(request.POST)

            if form.is_valid():
                cd = form.cleaned_data
                if not stub_account:
                    # make a new user that is active, but has not confirmed
                    # their email address
                    user = User.objects.create_user(
                        cd['username'],
                        cd['email'],
                        cd['password1']
                    )
                    up = UserProfile(user=user)
                else:
                    # Upgrade the stub account to make it a regular account.
                    user = stub_account
                    user.set_password(cd['password1'])
                    user.username = cd['username']
                    up = stub_account.profile
                    up.stub_account = False

                if cd['first_name']:
                    user.first_name = cd['first_name']
                if cd['last_name']:
                    user.last_name = cd['last_name']
                user.save()

                # Build and assign the activation key
                salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
                up.activation_key = hashlib.sha1(
                    salt + user.username).hexdigest()
                up.key_expires = now() + timedelta(days=5)
                up.save()

                email = emails['confirm_your_new_account']
                send_mail(
                    email['subject'],
                    email['body'] % (user.username, up.activation_key),
                    email['from'],
                    [user.email]
                )
                email = emails['new_account_created']
                send_mail(
                    email['subject'] % up.user.username,
                    email['body'] % (
                        up.user.get_full_name() or "Not provided",
                        up.user.email
                    ),
                    email['from'],
                    email['to'],
                )
                tally_stat('user.created')
                return HttpResponseRedirect(
                    '/register/success/?next=%s' % redirect_to)
        else:
            form = UserCreationFormExtended()
        return render_to_response("register/register.html",
                                  {'form': form, 'private': False},
                                  RequestContext(request))
    else:
        # The user is already logged in. Direct them to their settings page as
        # a logical fallback
        return HttpResponseRedirect('/profile/settings/')


@never_cache
def register_success(request):
    """Tell the user they have been registered and allow them to continue where
    they left off."""
    redirect_to = request.REQUEST.get('next', '')
    return render_to_response('register/registration_complete.html',
                              {'redirect_to': redirect_to, 'private': True},
                              RequestContext(request))


@never_cache
def confirm_email(request, activation_key):
    """Confirms email addresses for a user and sends an email to the admins.

    Checks if a hash in a confirmation link is valid, and if so validates the
    user's email address as valid.
    """
    ups = UserProfile.objects.filter(activation_key=activation_key)
    if not len(ups):
        return render_to_response('register/confirm.html',
                                  {'invalid': True, 'private': True},
                                  RequestContext(request))

    confirmed_accounts_count = 0
    expired_key_count = 0
    for up in ups:
        if up.email_confirmed:
            confirmed_accounts_count += 1
        if up.key_expires < now():
            expired_key_count += 1

    if confirmed_accounts_count == len(ups):
        # All the accounts were already confirmed.
        return render_to_response('register/confirm.html',
                                  {'already_confirmed': True, 'private': True},
                                  RequestContext(request))

    if expired_key_count > 0:
        return render_to_response('register/confirm.html',
                                  {'expired': True, 'private': True},
                                  RequestContext(request))

    # Tests pass; Save the profile
    for up in ups:
        up.email_confirmed = True
        up.save()

    return render_to_response(
        'register/confirm.html',
        {'success': True, 'private': True},
        RequestContext(request)
    )


@sensitive_variables('salt', 'activation_key', 'email_body')
@check_honeypot(field_name='skip_me_if_alive')
def request_email_confirmation(request):
    """Send an email confirmation email"""
    if request.method == 'POST':
        form = EmailConfirmationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            users = User.objects.filter(email__iexact=cd['email'])
            if not len(users):
                # Normally, we'd throw an error here, but we don't want to
                # reveal what accounts we have on file, so instead, we just
                # pretend like it worked.
                return HttpResponseRedirect('/email-confirmation/success/')

            # make a new activation key for all associated accounts.
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activation_key = hashlib.sha1(salt + cd['email']).hexdigest()
            key_expires = now() + timedelta(days=5)

            for user in users:
                # associate it with the user's accounts.
                up = user.profile
                up.activation_key = activation_key
                up.key_expires = key_expires
                up.save()

            email = emails['confirm_existing_account']
            send_mail(
                email['subject'],
                email['body'] % activation_key,
                email['from'],
                [user.email],
            )
            return HttpResponseRedirect('/email-confirmation/success/')
    else:
        form = EmailConfirmationForm()
    return render_to_response(
        'register/request_email_confirmation.html',
        {'private': True, 'form': form},
        RequestContext(request)
    )


@never_cache
def email_confirm_success(request):
    return render_to_response(
        'register/request_email_confirmation_success.html',
        {'private': False},
        RequestContext(request)
    )


@sensitive_post_parameters('old_password', 'new_password1', 'new_password2')
@login_required
@never_cache
def password_change(request):
    if request.method == "POST":
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            msg = message_dict['pwd_changed_successfully']
            messages.add_message(request, msg['level'], msg['message'])
            update_session_auth_hash(request, form.user)
            return HttpResponseRedirect('/profile/password/change/')
    else:
        form = CustomPasswordChangeForm(user=request.user)
    return render_to_response(
        'profile/password_form.html',
        {'form': form, 'private': False},
        RequestContext(request)
    )
