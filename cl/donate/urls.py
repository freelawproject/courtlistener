from django.urls import path

from cl.donate.paypal import donate_paypal_cancel, process_paypal_callback
from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import (
    badge_signup,
    cc_payment,
    donate,
    make_check_donation,
    payment_complete,
    toggle_monthly_donation,
)
from cl.users.views import view_donations

urlpatterns = [
    # Donations & payments
    path("donate/", donate, name="donate"),
    path("pay/", cc_payment, name="cc_payment"),
    path("badges/sign-up/", badge_signup, name="badge_signup"),
    path(
        "donate/complete/",
        payment_complete,
        {"template_name": "donate_complete.html"},
        name="donate_complete",
    ),
    path(
        "pay/complete/",
        payment_complete,
        {"template_name": "payment_complete.html"},
        name="payment_complete",
    ),
    path(
        "badges/complete/",
        payment_complete,
        {"template_name": "badge_signup_complete.html"},
        name="badge_signup_complete",
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
