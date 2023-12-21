from django.urls import path

from cl.donate.paypal import donate_paypal_cancel, process_paypal_callback
from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import payment_complete, toggle_monthly_donation

urlpatterns = [
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
    # Monthly donations
    path(
        "monthly-donation/toggle/",
        toggle_monthly_donation,
        name="toggle_monthly_donation",
    ),
]
