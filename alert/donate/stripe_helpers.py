from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import utc
import logging
import simplejson
import stripe
from alert.donate.models import Donation
from datetime import datetime
from django.conf import settings
from django.http import HttpResponseNotAllowed, HttpResponse

logger = logging.getLogger(__name__)


@csrf_exempt
def process_stripe_callback(request):
    if request.method == 'POST':
        # Stripe hits us with a callback, and their security model is for us
        # to use the ID from that to hit their API. It's analogous to when you
        # get a random call and you call them back to make sure it's legit.
        event_id = simplejson.loads(request.body)['id']
        # Now use the API to call back.
        stripe.api_key = settings.STRIPE_SECRET_KEY
        event = simplejson.loads(str(stripe.Event.retrieve(event_id)))
        logger.info('Stripe callback triggered. See webhook documentation for details.')
        if event['type'].startswith('charge') and \
                        event['livemode'] != settings.PAYMENT_TESTING_MODE:  # Livemode is opposite of testing mode
            charge = event['data']['object']
            d = get_object_or_404(Donation, payment_id=charge['id'])
            # See: https://stripe.com/docs/api#event_types
            if event['type'].endswith('succeeded'):
                d.clearing_date = datetime.utcfromtimestamp(charge['created']).replace(tzinfo=utc)
                d.status = 4
                from alert.donate.views import send_thank_you_email
                send_thank_you_email(d)
            elif event['type'].endswith('failed'):
                d.clearing_date = datetime.utcfromtimestamp(charge['created']).replace(tzinfo=utc)
                d.status = 1
            elif event['type'].endswith('refunded'):
                d.clearing_date = datetime.utcfromtimestamp(charge['created']).replace(tzinfo=utc)
                d.status = 7
            elif event['type'].endswith('captured'):
                d.clearing_date = datetime.utcfromtimestamp(charge['created']).replace(tzinfo=utc)
                d.status = 8
            elif event['type'].endswith('dispute.created'):
                logger.critical("Somebody has created a dispute in Stripe: %s" % charge['id'])
            elif event['type'].endswith('dispute.updated'):
                logger.critical("The Stripe dispute on charge %s has been updated." % charge['id'])
            elif event['type'].endswith('dispute.closed'):
                logger.critical("The Stripe dispute on charge %s has been closed." % charge['id'])
            d.save()
        return HttpResponse('<h1>200: OK</h1>')
    else:
        return HttpResponseNotAllowed(
            '<h1>405: This is a callback endpoint for a payment provider. '
            'Only POST methods are allowed.</h1>'
        )


def process_stripe_payment(cd_donation_form, cd_user_form, stripe_token):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create the charge on Stripe's servers
    try:
        charge = stripe.Charge.create(
            amount=int(cd_donation_form['amount']) * 100,  # amount in cents, watch yourself
            currency="usd",
            card=stripe_token,
            description=cd_user_form['email'],
        )
        response = {
            'message': None,
            'status': 0,  # Awaiting payment
            'payment_id': charge.id,
            'redirect': '/donate/stripe/complete',
        }
    except stripe.error.CardError, e:
        logger.warn("Stripe was unable to process the payment: %s" % e)
        response = {
            'message': 'Oops, we had a problem processing your card: '
                       '<strong>%s</strong>' %
                       e.json_body['error']['message'],
            'status': 1,  # ERROR
            'payment_id': None,
            'redirect': None,
        }

    return response
