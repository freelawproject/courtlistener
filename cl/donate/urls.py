from django.urls import path
from django.views.generic.base import RedirectView

from cl.donate.stripe_helpers import process_stripe_callback

urlpatterns = [
    # Stripe
    path(
        "donate/callbacks/stripe/",
        process_stripe_callback,
        name="stripe_callback",
    ),
]
