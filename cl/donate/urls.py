from django.conf.urls import url

from cl.donate.paypal import process_paypal_callback, donate_paypal_cancel
from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import donate, donate_complete, make_check_donation, \
    toggle_monthly_donation, cc_payment
from cl.users.views import view_donations

urlpatterns = [
    # Donations & payments
    url(r'^donate/$', donate, name="donate"),
    url(r'^pay/$', cc_payment, name="cc_payment"),

    # Paypal
    url(r'^donate/paypal/complete/$', donate_complete, name='paypal_complete'),
    url(r'^donate/paypal/cancel/$', donate_paypal_cancel),
    url(r'^donate/callbacks/paypal/$', process_paypal_callback),

    # Stripe
    url(r'^donate/stripe/complete/$', donate_complete, name='stripe_complete'),
    url(r'^donate/callbacks/stripe/$', process_stripe_callback,
        name='stripe_callback'),

    # Checks
    url(r'^donate/check/$', make_check_donation, name='make_check_donation'),
    url(r'^donate/check/complete/$', donate_complete, name='check_complete'),

    # Profile page
    url(r'^profile/donations/$', view_donations, name='profile_donations'),

    # Monthly donations
    url(r'^monthly-donation/toggle/$', toggle_monthly_donation,
        name='toggle_monthly_donation'),
]
