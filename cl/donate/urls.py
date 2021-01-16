from django.conf.urls import url

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
    url(r"^donate/$", donate, name="donate"),
    url(r"^pay/$", cc_payment, name="cc_payment"),
    url(r"^badges/sign-up/$", badge_signup, name="badge_signup"),
    url(
        r"^donate/complete/$",
        payment_complete,
        {"template_name": "donate_complete.html"},
        name="donate_complete",
    ),
    url(
        r"^pay/complete/$",
        payment_complete,
        {"template_name": "payment_complete.html"},
        name="payment_complete",
    ),
    url(
        r"^badges/complete/$",
        payment_complete,
        {"template_name": "badge_signup_complete.html"},
        name="badge_signup_complete",
    ),
    # Paypal
    url(
        r"^donate/paypal/cancel/$", donate_paypal_cancel, name="paypal_cancel"
    ),
    url(
        r"^donate/callbacks/paypal/$",
        process_paypal_callback,
        name="paypal_callback",
    ),
    # Stripe
    url(
        r"^donate/callbacks/stripe/$",
        process_stripe_callback,
        name="stripe_callback",
    ),
    # Checks
    url(r"^donate/check/$", make_check_donation, name="make_check_donation"),
    # Profile page
    url(r"^profile/donations/$", view_donations, name="profile_donations"),
    # Monthly donations
    url(
        r"^monthly-donation/toggle/$",
        toggle_monthly_donation,
        name="toggle_monthly_donation",
    ),
]
