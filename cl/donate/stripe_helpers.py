import json
import logging
import time
from datetime import datetime as dt
from datetime import timezone as tz
from typing import Dict, Optional, Union

import stripe
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from stripe.error import APIConnectionError
from stripe.stripe_object import StripeObject

from cl.donate.models import PROVIDERS, Donation
from cl.donate.types import StripeChargeObject, StripeEventObject
from cl.donate.utils import (
    PaymentFailureException,
    send_big_donation_email,
    send_thank_you_email,
)
from cl.users.utils import create_stub_account

logger = logging.getLogger(__name__)


def handle_external_payment_if_needed(charge: StripeChargeObject) -> None:
    """Gather data from a callback triggered by an external payment source

    When we send invoices to folks via Xero, they now have the option to make
    a payment via Stripe. When they do, it triggers our callback, but when that
    happens we don't know anything about the charge.

    Similarly, some people can only pay with Amex, which our website doesn't
    support, or only have an address outside the U.S. When this happens, we
    send them an invoice directly from Stripe itself. Since we do that, they
    lack a charge in our DB.

    Inspect the charge to see if these things are happening. If so, use the
    Stripe charge to add a user and a donation to the database.

    :param charge: A Stripe charge object: https://stripe.com/docs/api/charges
    :return: None
    """
    # Folks paying Xero invoices:
    xero_source = charge.get("application") == settings.XERO_APPLICATION_ID

    # Folks paying via Stripe invoices (these are useful for Amex or people
    # without an American address)
    stripe_source = charge["metadata"].get("type") == "invoice"
    if not any([xero_source, stripe_source]):
        # Just an average payment. Do the regular thing.
        return

    #
    # It's a weird source like xero.
    # Add a user and donation if needed.
    #
    billing_details = charge["billing_details"]
    email = billing_details["email"]
    if not email and stripe_source:
        # Webhooks triggered by Stripe invoices don't provide user information,
        # so we just file these all under the same fake user. 🤮
        email = "nobody@stripe.com"
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        user, _ = create_stub_account(
            {
                "email": email,
                # Stripe doesn't split up first/last name (smart), but we
                # do (doh). Just stuff it in the first_name field.
                "first_name": billing_details["name"],
                "last_name": "",
            },
            {
                "address1": billing_details["address"]["line1"],
                "address2": billing_details["address"]["line2"],
                "city": billing_details["address"]["city"],
                "state": billing_details["address"]["state"],
                "zip_code": billing_details["address"]["postal_code"],
                "wants_newsletter": False,
            },
        )
    if Donation.objects.filter(payment_id=charge["id"]).exists():
        # Don't create a payment if we already have one.
        return

    if xero_source:
        invoice_number = charge["metadata"]["Invoice number"]
        referrer = f"XERO invoice number: {invoice_number}"
    elif stripe_source:
        referrer = "Stripe invoice"
    else:
        raise NotImplementedError("Unknown source.")
    Donation.objects.create(
        donor=user,
        amount=float(charge["amount"]) / 100,  # Stripe does pennies.
        payment_provider=PROVIDERS.CREDIT_CARD,
        payment_id=charge["id"],
        status=Donation.AWAITING_PAYMENT,
        referrer=referrer,
    )


def get_donation_with_retries(
    event: StripeEventObject,
    charge: StripeChargeObject,
) -> Optional[Donation]:
    """Get the donation object from the DB

    Only fancy thing here is that the DB sometimes is slower than stripe can
    process transactions and send us a webhook. If that happens, we need a few
    retries.

    :param event: The stripe event in the webhook
    :param charge: The charge in the event
    :return: The donation object, or None if you can't find it
    """
    retry_count = 10
    d = None
    while retry_count > 0:
        try:
            if event["type"] in [
                "charge.dispute.created",
                "charge.dispute.funds_withdrawn",
                "charge.dispute.closed",
            ]:
                # I don't know why stripe doesn't use the "id" field on
                # disputes like they do everything else.
                d = Donation.objects.get(payment_id=charge["charge"])
            else:
                d = Donation.objects.get(payment_id=charge["id"])
        except Donation.DoesNotExist:
            time.sleep(1)
            retry_count -= 1
        else:
            break
    return d


def send_thank_you_if_needed(d: Donation, charge: StripeChargeObject) -> None:
    """Send a thank you to the user if called for

    :param d: The donation object
    :param charge: The charge from the stripe event
    :return: None
    """
    if charge["application"] == settings.XERO_APPLICATION_ID:
        # Don't send thank you's for Xero invoices
        return

    payment_type = charge["metadata"]["type"]
    recurring = charge["metadata"].get("recurring", False)
    send_thank_you_email(d, payment_type, recurring=recurring)
    send_big_donation_email(d, payment_type, recurring=recurring)


def update_donation_for_event(
    d: Optional[Donation],
    event: StripeEventObject,
    charge: StripeChargeObject,
) -> HttpResponse:
    """Take the values from the webhook and put them in our DB

    :param d: The Donation object or None
    :param event: The stripe event in the webhook
    :param charge: The charge from the event
    :return: The response to send to the webhook
    """
    # See: https://stripe.com/docs/api#event_types
    if not d:
        return HttpResponse(
            "<h1>200: No matching object in the "
            "database. No action needed.</h1>"
        )
    clearing_date = dt.utcfromtimestamp(charge["created"]).replace(
        tzinfo=tz.utc
    )
    if event["type"].endswith("succeeded"):
        d.clearing_date = clearing_date
        d.status = Donation.PROCESSED
        send_thank_you_if_needed(d, charge)
    elif event["type"].endswith("failed"):
        d.clearing_date = clearing_date
        d.status = Donation.AWAITING_PAYMENT
    elif event["type"].endswith("refunded"):
        d.clearing_date = clearing_date
        d.status = Donation.RECLAIMED_REFUNDED
    elif event["type"].endswith("captured"):
        d.clearing_date = clearing_date
        d.status = Donation.CAPTURED
    elif event["type"].endswith("dispute.created"):
        logger.info(f"Somebody has created a dispute: {charge['id']}")
        d.status = Donation.DISPUTED
    elif event["type"].endswith("dispute.updated"):
        logger.info(f"A dispute on charge {charge['id']} has been updated.")
    elif event["type"].endswith("dispute.funds_withdrawn"):
        logger.info(
            f"Funds for the stripe dispute on charge "
            f"{charge['charge']} have been withdrawn"
        )
    elif event["type"].endswith("dispute.closed"):
        logger.info(f"Dispute on charge {charge['charge']} has been closed.")
        d.status = Donation.DISPUTE_CLOSED
    d.save()
    return HttpResponse("<h1>200: OK</h1>")


@csrf_exempt  # nosemgrep
def process_stripe_callback(request: HttpRequest) -> HttpResponse:
    """Always return 200 message or else the webhook will try again ~200 times
    and then send us an email.
    """
    if request.method == "POST":
        # Stripe hits us with a callback, and their security model is for us
        # to use the ID from that to hit their API. It's analogous to when you
        # get a random call and you call them back to make sure it's legit.
        event_id = json.loads(request.body)["id"]
        # Now use the API to call back.
        stripe.api_key = settings.STRIPE_SECRET_KEY
        event = json.loads(str(stripe.Event.retrieve(event_id)))
        logger.info(
            f"Stripe callback triggered with event id of {event_id}. See "
            "webhook documentation for details."
        )
        is_charge = event["type"].startswith("charge")
        is_live = event["livemode"] != settings.DEVELOPMENT
        if all([is_charge, is_live]):
            charge = event["data"]["object"]

            handle_external_payment_if_needed(charge)
            d = get_donation_with_retries(event, charge)
            return update_donation_for_event(d, event, charge)
        return HttpResponse("<h1>200: OK</h1>")
    return HttpResponseNotAllowed(
        permitted_methods={"POST"},
        content="<h1>405: This is a callback endpoint for a payment "
        "provider. Only POST methods are allowed.</h1>",
    )


def process_stripe_payment(
    amount: int,
    email: str,
    kwargs: Dict[str, Union[str, bool, Dict[str, str]]],
    stripe_redirect_url: str,
) -> Dict[str, Union[str, int]]:
    """Process a stripe payment.

    :param amount: The amount, in pennies, that you wish to charge
    :param email: The email address of the person being charged
    :param kwargs: Keyword arguments to pass to Stripe's `create` method. Some
    functioning options for this dict are:

        {'card': stripe_token}

    And:

        {'customer': customer.id}

    Where stripe_token is a token returned by Stripe's client-side JS library,
    and customer is an object returned by stripe's customer creation server-
    side library.

    :param stripe_redirect_url: Where to send the user after a successful
    transaction
    :return: response object with information about whether the transaction
    succeeded.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create the charge on Stripe's servers
    try:
        charge = stripe.Charge.create(
            amount=amount, currency="usd", description=email, **kwargs
        )
        response = {
            "status": Donation.AWAITING_PAYMENT,
            "payment_id": charge.id,
            "redirect": stripe_redirect_url,
        }
    except (stripe.error.CardError, stripe.error.InvalidRequestError) as e:
        logger.info(f"Stripe was unable to process the payment: {e}")
        message = (
            "Oops, we had an error with your donation: "
            "<strong>%s</strong>" % e.json_body["error"]["message"]
        )
        raise PaymentFailureException(message)

    return response


def create_stripe_customer(source: str, email: str) -> StripeObject:
    """Create a stripe customer so that we can charge this person more than
    once

    :param source: The stripe token to use for the creation
    :param email: The customer's email address
    :return: A stripe customer object
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        return stripe.Customer.create(source=source, email=email)
    except (stripe.error.CardError, stripe.error.InvalidRequestError) as e:
        logger.warning(f"Stripe was unable to create the customer: {e}")
        message = (
            "Oops, we had an error with your donation: "
            "<strong>%s</strong>" % e.json_body["error"]["message"]
        )
        raise PaymentFailureException(message)
    except APIConnectionError:
        logger.warning("Unable to connect to stripe to create customer.")
        raise PaymentFailureException(
            "Oops. We were unable to connect to our payment provider. "
            "Please try again. If this error continues, please try again "
            "later."
        )
