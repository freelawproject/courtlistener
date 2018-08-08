import json
import logging
from datetime import datetime

import stripe
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseNotAllowed, HttpResponse
from django.utils.timezone import utc
from django.views.decorators.csrf import csrf_exempt

from cl.donate.models import Donation
from cl.donate.utils import send_thank_you_email

logger = logging.getLogger(__name__)


@csrf_exempt
def process_stripe_callback(request):
    """Always return 200 message or else the webhook will try again ~200 times
    and then send us an email.
    """
    if request.method == 'POST':
        # Stripe hits us with a callback, and their security model is for us
        # to use the ID from that to hit their API. It's analogous to when you
        # get a random call and you call them back to make sure it's legit.
        event_id = json.loads(request.body)['id']
        # Now use the API to call back.
        stripe.api_key = settings.STRIPE_SECRET_KEY
        event = json.loads(str(stripe.Event.retrieve(event_id)))
        logger.info('Stripe callback triggered. See webhook documentation for '
                    'details.')
        if event['type'].startswith('charge') and \
                event['livemode'] != settings.PAYMENT_TESTING_MODE:
            charge = event['data']['object']
            try:
                d = Donation.objects.get(payment_id=charge['id'])
            except Donation.DoesNotExist:
                d = None

            # See: https://stripe.com/docs/api#event_types
            if event['type'].endswith('succeeded'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.PROCESSED
                send_thank_you_email(d)
            elif event['type'].endswith('failed'):
                if not d:
                    return HttpResponse('<h1>200: No matching object in the '
                                        'database. No action needed.</h1>')
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.AWAITING_PAYMENT
            elif event['type'].endswith('refunded'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.RECLAIMED_REFUNDED
            elif event['type'].endswith('captured'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.CAPTURED
            elif event['type'].endswith('dispute.created'):
                logger.critical("Somebody has created a dispute in "
                                "Stripe: %s" % charge['id'])
            elif event['type'].endswith('dispute.updated'):
                logger.critical("The Stripe dispute on charge %s has been "
                                "updated." % charge['id'])
            elif event['type'].endswith('dispute.closed'):
                logger.critical("The Stripe dispute on charge %s has been "
                                "closed." % charge['id'])
            d.save()
        return HttpResponse('<h1>200: OK</h1>')
    else:
        return HttpResponseNotAllowed(
            permitted_methods={'POST'},
            content='<h1>405: This is a callback endpoint for a payment '
                    'provider. Only POST methods are allowed.</h1>'
        )


def process_stripe_payment(cd_donation_form, cd_user_form, kwargs):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create the charge on Stripe's servers
    try:
        charge = stripe.Charge.create(
            amount=int(float(cd_donation_form['amount']) * 100),  # amount in cents, watch yourself
            currency="usd",
            description=cd_user_form['email'],
            **kwargs
        )
        response = {
            'message': None,
            'status': Donation.AWAITING_PAYMENT,
            'payment_id': charge.id,
            'redirect': reverse('stripe_complete'),
        }
    except stripe.error.CardError as e:
        logger.warn("Stripe was unable to process the payment: %s" % e)
        response = {
            'message': 'Oops, we had a problem processing your card: '
                       '<strong>%s</strong>' % e.json_body['error']['message'],
            'status': Donation.UNKNOWN_ERROR,
            'payment_id': None,
            'redirect': None,
        }
    except stripe.error.InvalidRequestError as e:
        logger.warn("Stripe was unable to process the payment: %s" % e)
        response = {
            'message': 'Oops, we had an error with your donation: '
                       '<strong>%s</strong>' % e.json_body['error']['message'],
            'status': Donation.UNKNOWN_ERROR,
            'payment_id': None,
            'redirect': None,
        }

    return response


def create_stripe_customer(source, email):
    """Create a stripe customer so that we can charge this person more than
    once
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    return stripe.Customer.create(source=source, email=email)
