from django.urls import path

from cl.donate.paypal import donate_paypal_cancel, process_paypal_callback
from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import (
    donate,
    make_check_donation,
    payment_complete,
    toggle_monthly_donation,
)
from cl.users.views import view_donations

urlpatterns = [
    # Donations & payments
    path("donate/", donate, name="donate"),
    path(
        "donate/complete/",
        payment_complete,
        {"template_name": "donate_complete.html"},
        name="donate_complete",
    ),
    # Paypal
    path("donate/paypal/cancel/", donate_paypal_cancel, name="paypal_cancel"),
    path(
        "donate/callbacks/paypal/",
        process_paypal_callback,
        name="paypal_callback",
    ),
    # Stripe
    path(
        "donate/callbacks/stripe/",
        process_stripe_callback,
        name="stripe_callback",
    ),
    # Checks
    path("donate/check/", make_check_donation, name="make_check_donation"),
    # Profile page
    path("profile/donations/", view_donations, name="profile_donations"),
    # Monthly donations
    path(
        "monthly-donation/toggle/",
        toggle_monthly_donation,
        name="toggle_monthly_donation",
    ),
]
