from cl.donate.paypal import process_paypal_callback, donate_paypal_cancel
from cl.donate.sitemap import donate_sitemap_maker
from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import donate, donate_complete
from cl.users.views import view_donations
from django.conf.urls import url

urlpatterns = [
    # Donations
    url(r'^donate/$', donate),

    # Paypal
    url(r'^donate/paypal/complete/$', donate_complete),
    url(r'^donate/paypal/cancel/$', donate_paypal_cancel),
    url(r'^donate/callbacks/paypal/$', process_paypal_callback),

    # Stripe
    url(r'^donate/stripe/complete/$', donate_complete),
    url(r'^donate/callbacks/stripe/$', process_stripe_callback),

    # Profile page
    url(r'^profile/donations/$', view_donations),

    # Sitemap:
    url(r'^sitemap-donate\.xml$', donate_sitemap_maker),
]
