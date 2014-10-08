from alert.donate.dwolla import process_dwolla_callback, \
    process_dwolla_transaction_status_callback
from alert.donate.paypal import process_paypal_callback, donate_paypal_cancel
from alert.donate.sitemap import donate_sitemap_maker
from alert.donate.stripe_helpers import process_stripe_callback
from alert.donate.views import donate, donate_complete, view_donations
from django.conf.urls import patterns


urlpatterns = patterns('',
    # Donations
    (r'^donate/$', donate),
    (r'^donate/dwolla/complete/$', donate_complete),
    (r'^donate/paypal/complete/$', donate_complete),
    (r'^donate/stripe/complete/$', donate_complete),
    (r'^donate/callbacks/dwolla/$', process_dwolla_callback),
    (r'^donate/callbacks/dwolla/transaction-status/$',
     process_dwolla_transaction_status_callback),
    (r'^donate/callbacks/paypal/$', process_paypal_callback),
    (r'^donate/callbacks/stripe/$', process_stripe_callback),
    (r'^donate/paypal/cancel/$', donate_paypal_cancel),

    # Profile page
    (r'^profile/donations/$', view_donations),

    # Sitemap:
    (r'^sitemap-donate\.xml$', donate_sitemap_maker),
)
