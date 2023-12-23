from django.urls import path
from django.views.generic.base import RedirectView

from cl.donate.stripe_helpers import process_stripe_callback

urlpatterns = [
    path(
        "donate/",
        RedirectView.as_view(url="https://free.law/donate"),
    ),
    # Stripe
    path(
        "donate/callbacks/stripe/",
        process_stripe_callback,
        name="stripe_callback",
    ),
]
