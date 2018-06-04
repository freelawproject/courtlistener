import hashlib
import logging
import random
import re
from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template.defaultfilters import urlencode
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import (sensitive_post_parameters,
                                           sensitive_variables)

from cl.custom_filters.decorators import check_honeypot
from cl.favorites.forms import FavoriteForm
from cl.lib import search_utils
from cl.stats.utils import tally_stat
from cl.users.forms import (
    ProfileForm, UserForm, UserCreationFormExtended, EmailConfirmationForm,
    CustomPasswordChangeForm, OptInConsentForm,
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
    return render(request, 'profile/alerts.html', {
        'alerts': alerts,
        'private': True
    })


@login_required
@never_cache
def view_favorites(request):
    favorites = request.user.favorites.all().order_by('pk')
    favorite_forms = []
    for favorite in favorites:
        favorite_forms.append(FavoriteForm(instance=favorite))
    return render(request, 'profile/favorites.html', {
        'private': True,
        'favorite_forms': favorite_forms,
        'blank_favorite_form': FavoriteForm()
    })


@login_required
@never_cache
def view_donations(request):
    return render(request, 'profile/donations.html', {'private': True})


@login_required
@never_cache
def view_visualizations(request):
    visualizations = SCOTUSMap.objects.filter(
        user=request.user,
        deleted=False,
    ).annotate(
        Count('clusters'),
    ).order_by(
        '-date_created',
    )
    paginator = Paginator(visualizations, 20, orphans=2)
    page = request.GET.get('page', 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)
    return render(request, 'profile/visualizations.html', {
        'results': paged_vizes,
        'private': True,
    })


@login_required
@never_cache
def view_deleted_visualizations(request):
    thirty_days_ago = now() - timedelta(days=30)
    visualizations = SCOTUSMap.objects.filter(
        user=request.user,
        deleted=True,
        date_deleted__gte=thirty_days_ago,
    ).annotate(
        Count('clusters'),
    ).order_by(
        '-date_created',
    )
    paginator = Paginator(visualizations, 20, orphans=2)
    page = request.GET.get('page', 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)

    return render(request, 'profile/visualizations_deleted.html', {
        'results': paged_vizes,
        'private': True,
    })


@login_required
@never_cache
def view_api(request):
    return render(request, 'profile/api.html', {'private': True})


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
    return render(request, 'profile/settings.html', {
        'profile_form': profile_form,
        'user_form': user_form,
        'private': True
    })


@login_required
def delete_account(request):
    if request.method == 'POST':
        try:
            email = emails['account_deleted']
            send_mail(email['subject'], email['body'] % request.user,
                      email['from'], email['to'])
            request.user.alerts.all().delete()
            request.user.favorites.all().delete()
            request.user.scotus_maps.all().update(deleted=True)
            convert_to_stub_account(request.user)
            logout(request)

        except Exception as e:
            logger.critical("User was unable to delete account. %s" % e)

        return HttpResponseRedirect(reverse('delete_profile_done'))

    non_deleted_map_count = request.user.scotus_maps.filter(deleted=False).count()
    return render(request, 'profile/delete.html', {
        'non_deleted_map_count': non_deleted_map_count,
        'private': True
    })


def delete_profile_done(request):
    return render(request, 'profile/deleted.html', {'private': True})


@login_required
def take_out(request):
    if request.method == 'POST':
        email = emails['take_out_requested']
        send_mail(
            email['subject'],
            email['body'] % (request.user, request.user.email),
            email['from'],
            email['to'],
        )

        return HttpResponseRedirect(reverse('take_out_done'))

    return render(request, 'profile/take_out.html', {
        'private': True
    })


def take_out_done(request):
    return render(request, 'profile/take_out_done.html', {'private': True})


@sensitive_post_parameters('password1', 'password2')
@sensitive_variables('salt', 'activation_key', 'email_body')
@check_honeypot(field_name='skip_me_if_alive')
@never_cache
def register(request):
    """allow only an anonymous user to register"""
    redirect_to = request.GET.get('next', '')
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

            consent_form = OptInConsentForm(request.POST)
            if form.is_valid() and consent_form.is_valid():
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
                get_str = '?next=%s&email=%s' % (urlencode(redirect_to),
                                                 urlencode(user.email))
                return HttpResponseRedirect(reverse('register_success') +
                                            get_str)
        else:
            form = UserCreationFormExtended()
            consent_form = OptInConsentForm()
        return render(request, "register/register.html", {
            'form': form,
            'consent_form': consent_form,
            'private': False
        })
    else:
        # The user is already logged in. Direct them to their settings page as
        # a logical fallback
        return HttpResponseRedirect(reverse('view_settings'))


@never_cache
def register_success(request):
    """Tell the user they have been registered and allow them to continue where
    they left off."""
    redirect_to = request.GET.get('next', '')
    email = request.GET.get('email', '')
    default_from = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    return render(request, 'register/registration_complete.html', {
        'redirect_to': redirect_to,
        'email': email,
        'default_from': default_from,
        'private': True,
    })


@never_cache
def confirm_email(request, activation_key):
    """Confirms email addresses for a user and sends an email to the admins.

    Checks if a hash in a confirmation link is valid, and if so validates the
    user's email address as valid.
    """
    ups = UserProfile.objects.filter(activation_key=activation_key)
    if not len(ups):
        return render(request, 'register/confirm.html', {
            'invalid': True,
            'private': True
        })

    confirmed_accounts_count = 0
    expired_key_count = 0
    for up in ups:
        if up.email_confirmed:
            confirmed_accounts_count += 1
        if up.key_expires < now():
            expired_key_count += 1

    if confirmed_accounts_count == len(ups):
        # All the accounts were already confirmed.
        return render(request, 'register/confirm.html', {
            'already_confirmed': True,
            'private': True
        })

    if expired_key_count > 0:
        return render(request, 'register/confirm.html', {
            'expired': True,
            'private': True
        })

    # Tests pass; Save the profile
    for up in ups:
        up.email_confirmed = True
        up.save()

    return render(request, 'register/confirm.html', {
        'success': True,
        'private': True
    })


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
                return HttpResponseRedirect(reverse('email_confirm_success'))

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
            return HttpResponseRedirect(reverse('email_confirm_success'))
    else:
        form = EmailConfirmationForm()
    return render(request, 'register/request_email_confirmation.html', {
        'private': True,
        'form': form
    })


@never_cache
def email_confirm_success(request):
    return render(request, 'register/request_email_confirmation_success.html', {
        'private': False
    })


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
            return HttpResponseRedirect(reverse('password_change'))
    else:
        form = CustomPasswordChangeForm(user=request.user)
    return render(request, 'profile/password_form.html', {
        'form': form,
        'private': False
    })
