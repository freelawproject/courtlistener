import logging

from cl.donate.paypal import process_paypal_payment
from cl.donate.forms import DonationForm, UserForm, ProfileForm
from cl.donate.stripe_helpers import process_stripe_payment
from cl.users.utils import create_stub_account
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

logger = logging.getLogger(__name__)


def send_thank_you_email(donation):
    user = donation.donor
    email_subject = 'Thanks for your donation to Free Law Project!'
    email_body = ('Hello %s,\n\nThanks for your donation of $%0.2f to Free '
                  'Law Project. We are currently using donations like yours '
                  'for a variety of important projects that would never exist '
                  'without your help.\n\n'

                  'We are a federally-recognized 501(c)(3) public charity '
                  'and a California non-profit public benefit corporation. '
                  'Our EIN is %s.\n\n'

                  'If you have any questions about your donation, please '
                  'don\'t hesitate to get in touch.\n\n'

                  'Thanks again,\n\n'
                  'Michael Lissner and Brian Carver\n'
                  'Founders of Free Law Project\n'
                  'https://free.law/contact/') % \
                 (user.first_name, donation.amount, settings.EIN, )
    send_mail(
        email_subject,
        email_body,
        'Free Law Project <donate@free.law>',
        [user.email]
    )


def route_and_process_donation(cd_donation_form, cd_user_form, stripe_token):
    """Routes the donation to the correct payment provider, then normalizes
    its response.

    Returns a dict with:
     - message: Any error messages that apply
     - status: The status of the payment for the database
     - payment_id: The ID of the payment
    """
    if cd_donation_form['payment_provider'] == 'paypal':
        response = process_paypal_payment(cd_donation_form)
        if response['result'] == 'created':
            response = {
                'message': None,
                'status': 0,  # AWAITING_PAYMENT
                'payment_id': response['payment_id'],
                'transaction_id': response['transaction_id'],
                'redirect': response['redirect'],
            }
        else:
            response = {
                'message': 'We had an error working with PayPal. Please try '
                           'another payment method.',
                'status': 1,  # ERROR
                'payment_id': None,
                'redirect': None,
            }
    elif cd_donation_form['payment_provider'] == 'cc':
        response = process_stripe_payment(
            cd_donation_form,
            cd_user_form,
            stripe_token
        )
    else:
        response = None
    return response


def donate(request):
    """Load the donate page or process a submitted donation.

    This page has several branches. The logic is as follows:
        if GET:
            --> Load the page
        elif POST:
            if user is anonymous:
                if email address on record as a stub account:
                    --> Use it.
                elif new email address or a non-stub account:
                    --> We cannot allow anonymous people to update real
                        accounts, or this is a new email address, so create a
                        new stub account.
            elif user is logged in:
                --> associate with account.

            We now have an account. Process the payment and associate it.
    """

    message = None
    if request.method == 'POST':
        donation_form = DonationForm(request.POST)

        if request.user.is_anonymous():
            # Either this is a new account, a stubbed one, or a user that's
            # simply not logged into their account
            try:
                stub_account = User.objects.filter(
                    profile__stub_account=True
                ).get(
                    email__iexact=request.POST.get('email')
                )
            except User.DoesNotExist:
                stub_account = False

            if stub_account:
                # We use the stub account and anonymous users even are allowed
                # to update it. This is OK, because we don't care too much
                # about the accuracy of this data. Later if/when this becomes
                # a real account, anonymous users won't be able to update this
                # information -- that's what matters.
                user_form = UserForm(
                    request.POST,
                    instance=stub_account
                )
                profile_form = ProfileForm(
                    request.POST,
                    instance=stub_account.profile
                )
            else:
                # Either a regular account or an email address we've never
                # seen before. Create a new user from the POST data.
                user_form = UserForm(request.POST)
                profile_form = ProfileForm(request.POST)
        else:
            user_form = UserForm(
                request.POST,
                instance=request.user
            )
            profile_form = ProfileForm(
                request.POST,
                instance=request.user.profile
            )

        if all([donation_form.is_valid(),
                user_form.is_valid(),
                profile_form.is_valid()]):
            # Process the data in form.cleaned_data
            cd_donation_form = donation_form.cleaned_data
            cd_user_form = user_form.cleaned_data
            cd_profile_form = profile_form.cleaned_data
            stripe_token = request.POST.get('stripeToken')

            # Route the payment to a payment provider
            response = route_and_process_donation(
                cd_donation_form,
                cd_user_form,
                stripe_token
            )
            logger.info("Payment routed with response: %s" % response)

            if response['status'] == 0:
                if request.user.is_anonymous() and not stub_account:
                    # Create a stub account with an unusable password
                    user, profile = create_stub_account(
                        cd_user_form,
                        cd_profile_form,
                    )
                    user.save()
                    profile.save()
                else:
                    # Logged in user or an existing stub account.
                    user = user_form.save()
                    profile = profile_form.save()

                d = donation_form.save(commit=False)
                d.status = response['status']
                d.payment_id = response['payment_id']
                d.transaction_id = response.get('transaction_id')  # Will only work for Paypal.
                d.donor = user
                d.save()

                return HttpResponseRedirect(response['redirect'])

            else:
                logger.critical("Got back status of %s when making initial "
                                "request of API. Message was:\n%s" %
                                (response['status'], response['message']))
                message = response['message']
    else:
        # Loading the page...
        try:
            donation_form = DonationForm(
                initial={
                    'referrer': request.GET.get('referrer')
                }
            )
            user_form = UserForm(
                initial={
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'email': request.user.email,
                }
            )
            up = request.user.profile
            profile_form = ProfileForm(
                initial={
                    'address1': up.address1,
                    'address2': up.address2,
                    'city': up.city,
                    'state': up.state,
                    'zip_code': up.zip_code,
                    'wants_newsletter': up.wants_newsletter
                }
            )
        except AttributeError:
            # for anonymous users, who lack profile info
            user_form = UserForm()
            profile_form = ProfileForm()

    return render_to_response(
        'donate.html',
        {
            'donation_form': donation_form,
            'user_form': user_form,
            'profile_form': profile_form,
            'private': False,
            'message': message,
            'stripe_public_key': settings.STRIPE_PUBLIC_KEY
        },
        RequestContext(request)
    )


def donate_complete(request):
    error = None
    if len(request.GET) > 0:
        # We've gotten some information from the payment provider
        if request.GET.get('error') == 'failure':
            if request.GET.get('error_description') == 'User Cancelled':
                error = 'User Cancelled'
            elif 'insufficient funds' in request.GET.get('error_description').lower():
                error = 'Insufficient Funds'
            return render_to_response(
                'donate_complete.html',
                {
                    'error': error,
                    'private': True,
                },
                RequestContext(request),
            )

    return render_to_response(
        'donate_complete.html',
        {
            'error': error,
            'private': True,
        },
        RequestContext(request)
    )
