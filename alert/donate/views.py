from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.cache import never_cache
from alert.donate.dwolla import process_dwolla_payment
from alert.donate.paypal import process_paypal_payment
from alert.donate.forms import DonationForm, UserForm, ProfileForm
from alert.donate.stripe_helpers import process_stripe_payment
from alert.userHandling.models import UserProfile

import logging

logger = logging.getLogger(__name__)


@login_required
@never_cache
def view_donations(request):
    return render_to_response('profile/donations.html',
                              {'private': False},
                              RequestContext(request))


def send_thank_you_email(donation):
    profile = donation.userprofile_set.all()[0]
    email_subject = 'Thanks for your donation to the Free Law Project!'
    email_body = ('Hello %s,\n\nThanks for your donation of $%0.2f to the Free Law Project. We are currently using '
                  'donations like yours for a variety of important projects that would never exist without your '
                  'help.\n\n'
                  'We are currently a California non-profit corporation, and we hope to soon receive recognition '
                  'as a federally recognized 501(c)(3) non-profit. Our EIN is %s.\n\n'
                  'If you have any questions about your donation, please don\'t hesitate to get in touch.\n\n'
                  'Thanks again,\n\n'
                  'Michael Lissner and Brian Carver\n'
                  'Founders of Free Law Project\n'
                  'http://freelawproject.org/contact/') % (profile.user.first_name, donation.amount, settings.EIN, )
    send_mail(email_subject, email_body, 'Free Law Project <donate@freelawproject.org>', [profile.user.email])


def route_and_process_donation(cd_donation_form, cd_profile_form, cd_user_form, stripe_token):
    """Routes the donation to the correct payment provider, then normalizes its response.

    Returns a dict with:
     - message: Any error messages that apply
     - status: The status of the payment for the database
     - payment_id: The ID of the payment
    """
    if cd_donation_form['payment_provider'] == 'dwolla':
        # Bad response:  '{"Result":"Failure","Message":"Invalid application credentials."}'
        # Good response: '{"Result":"Success","CheckoutId":"aba88bed-b525-48a4-93fd-9f7d1ec3f57b"}'
        response = process_dwolla_payment(
            cd_donation_form,
            cd_profile_form,
            cd_user_form,
            test=settings.PAYMENT_TESTING_MODE
        )
        if response['result'] == 'Success':
            response = {
                'message': None,  # Dwolla has no messages when successful
                'status': 0,  # AWAITING_PAYMENT
                'payment_id': response['payment_id'],
                'redirect': response['redirect']
            }
        else:
            response = {
                'message': response['message'],
                'status': 1,  # ERROR
                'payment_id': None,
                'redirect': None,
            }
    elif cd_donation_form['payment_provider'] == 'paypal':
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
                'message': 'We had an error working with PayPal. Please try another payment method.',
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
    message = None
    if request.method == 'POST':
        donation_form = DonationForm(request.POST)
        stub_account = False

        if request.user.is_anonymous():
            # Either this is a new account, a stubbed one, or a user that's simply not logged into their account
            try:
                stub_account = User.objects.filter(profile__stub_account=True). \
                                            get(email__iexact=request.POST.get('email'))
            except User.DoesNotExist:
                pass

            if not stub_account:
                user_form = UserForm(request.POST)
                profile_form = ProfileForm(request.POST)
            else:
                # We use the stub account and anonymous users even are allowed to update it. This is OK, because we
                # don't care too much about the accuracy of this data. Later if/when this becomes a real account,
                # anonymous users won't be able to update this information -- that's what matters.
                user_form = UserForm(request.POST, instance=stub_account)
                profile_form = ProfileForm(request.POST, instance=stub_account.profile)
        else:
            user_form = UserForm(request.POST, instance=request.user)
            profile_form = ProfileForm(request.POST, instance=request.user.profile)

        if all([donation_form.is_valid(), user_form.is_valid(), profile_form.is_valid()]):
            # Process the data in form.cleaned_data
            cd_donation_form = donation_form.cleaned_data
            cd_user_form = user_form.cleaned_data
            cd_profile_form = profile_form.cleaned_data
            stripe_token = request.POST.get('stripeToken')

            # Route the payment to a payment provider
            response = route_and_process_donation(cd_donation_form, cd_profile_form, cd_user_form, stripe_token)
            logger.info("Payment routed with response: %s" % response)

            if response['status'] == 0:
                d = donation_form.save(commit=False)
                d.status = response['status']
                d.payment_id = response['payment_id']
                d.transaction_id = response.get('transaction_id')  # Will onlyl work for Paypal.
                d.save()

                if request.user.is_anonymous() and not stub_account:
                    # Create a stub account with an unusable password
                    new_user = User.objects.create_user(
                        cd_user_form['email'][:30],  # Username can only be 30 chars long
                        cd_user_form['email'],
                    )
                    new_user.first_name = cd_user_form['first_name']
                    new_user.last_name = cd_user_form['last_name']
                    new_user.save()
                    profile = UserProfile(
                        user=new_user,
                        stub_account=True,
                        address1=cd_profile_form['address1'],
                        address2=cd_profile_form.get('address2'),
                        city=cd_profile_form['city'],
                        state=cd_profile_form['state'],
                        zip_code=cd_profile_form['zip_code'],
                        wants_newsletter=cd_profile_form['wants_newsletter']
                    )
                    profile.save()
                else:
                    # Logged in user or an existing stub account.
                    user = user_form.save()
                    profile = profile_form.save()

                # Associate the donation with the profile
                profile.donation.add(d)
                profile.save()
                return HttpResponseRedirect(response['redirect'])

            else:
                logger.critical("Got back status of %s when making initial request of API. Message was:\n%s" %
                                (response['status'], response['message']))
                message = response['message']
    else:
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
        'donate/donate.html',
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
                'donate/donate_complete.html',
                {
                    'error': error,
                    'private': True,
                },
                RequestContext(request),
            )

    return render_to_response(
        'donate/donate_complete.html',
        {
            'error': error,
            'private': True,
        },
        RequestContext(request)
    )
