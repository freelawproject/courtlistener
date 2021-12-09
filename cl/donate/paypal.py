import logging
from http import HTTPStatus
from typing import Dict
from urllib.parse import parse_qs, urlparse

import requests
import simplejson as json  # This is needed to handle Decimal objects.
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt

from cl.donate.forms import CleanedDonationFormType
from cl.donate.models import PAYMENT_TYPES, Donation
from cl.donate.utils import (
    PaymentFailureException,
    send_big_donation_email,
    send_thank_you_email,
)

logger = logging.getLogger(__name__)


def get_paypal_access_token() -> str:
    """Get a token for the PayPal API.

    Query the PayPal API to get an access token. This could be improved by
    caching the token and detecting when it is expired.
    """
    r = requests.post(
        f"{settings.PAYPAL_ENDPOINT}/v1/oauth2/token",
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET_KEY),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if r.status_code == HTTPStatus.OK:
        logger.info("Got paypal token successfully.")
    else:
        logger.warning(
            "Problem getting paypal token status_code was: %s, "
            "with content: %s" % (r.status_code, r.text)
        )
        raise PaymentFailureException(
            "Oops, sorry. PayPal had an error. Please try again."
        )
    return json.loads(r.content).get("access_token")


@csrf_exempt  # nosemgrep
def process_paypal_callback(request: HttpRequest) -> HttpResponse:
    """Process the GET request that PayPal uses.

    After a transaction is completed, PayPal sends the user back to a page on
    our site. This could be our "Thanks" page, but since that page is seen by
    all the payment providers, instead this is an intermediate page, where we
    grab the correct things from the URL, process the item, and then shuttle
    the user off to the normal "Thanks" page.

    The other providers do this via a POST rather than a GET, so that's why
    this one is a bit of an oddball.
    """
    try:
        access_token = get_paypal_access_token()
    except PaymentFailureException as e:
        logger.info(f"Unable to get PayPal access token. Message was: {e}")
        return HttpResponse(status=HTTPStatus.SERVICE_UNAVAILABLE)

    d = Donation.objects.get(transaction_id=request.GET["token"])
    r = requests.post(
        f"{settings.PAYPAL_ENDPOINT}/v1/payments/payment/{d.payment_id}/execute/",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        data=json.dumps({"payer_id": request.GET["PayerID"]}),
        timeout=30,
    )
    if r.status_code == HTTPStatus.OK:
        d.clearing_date = now()
        # Technically, this should be d.status = 2 (Completed, awaiting
        # processing) and we should await a webhook to tell us that the
        # processing completed successfully (4). Alas, PayPal is so terrible
        # that I can't figure that out, so we just assume that if it gets
        # completed (2), it'll get processed (4).
        d.status = Donation.PROCESSED
        d.save()
        send_thank_you_email(d, payment_type=PAYMENT_TYPES.DONATION)
        send_big_donation_email(d, payment_type=PAYMENT_TYPES.DONATION)
    else:
        if (
            r.status_code == HTTPStatus.BAD_REQUEST
            and r.json().get("name") == "INSTRUMENT_DECLINED"
        ):
            d.status = Donation.FAILED
            d.save()
            return render(
                request,
                "donate_complete.html",
                {"error": "declined", "private": True},
            )
        else:
            logger.critical(
                "Unable to execute PayPal transaction. Status code %s "
                "with data: %s" % (r.status_code, r.text)
            )
            d.status = Donation.UNKNOWN_ERROR
            d.save()
    # Finally, show them the thank you page
    return HttpResponseRedirect(reverse("donate_complete"))


def process_paypal_payment(
    cd_donation_form: CleanedDonationFormType,
) -> Dict[str, str]:
    # https://developer.paypal.com/webapps/developer/docs/integration/web/accept-paypal-payment/
    access_token = get_paypal_access_token()
    if not access_token:
        raise PaymentFailureException("NO_ACCESS_TOKEN")

    return_url = f"https://www.courtlistener.com{reverse('paypal_callback')}"
    cancel_url = f"https://www.courtlistener.com{reverse('paypal_cancel')}"
    data = {
        "intent": "sale",
        "redirect_urls": {"return_url": return_url, "cancel_url": cancel_url},
        "payer": {"payment_method": "paypal"},
        "transactions": [
            {
                "amount": {
                    "total": cd_donation_form["amount"],
                    "currency": "USD",
                },
                "description": "Donation to Free Law Project",
            }
        ],
    }
    r = requests.post(
        f"{settings.PAYPAL_ENDPOINT}/v1/payments/payment",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        data=json.dumps(data),
        timeout=30,
    )

    if r.status_code == HTTPStatus.CREATED:
        r_content_as_dict = json.loads(r.content)
        # Get the redirect value from the 'links' attribute. Links look like:
        #   [{u'href': u'https://api.sandbox.paypal.com/v1/payments/payment/PAY-8BC403022U6413151KIQPC2I',
        #     u'method': u'GET',
        #     u'rel': u'self'},
        #    {u'href': u'https://www.sandbox.paypal.com/cgi-bin/webscr?cmd=_express-checkout&token=EC-6VV58324J9479725S',
        #     u'method': u'REDIRECT',
        #     u'rel': u'approval_url'},
        #    {u'href': u'https://api.sandbox.paypal.com/v1/payments/payment/PAY-8BC403022U6413151KIQPC2I/execute',
        #     u'method': u'POST',
        #     u'rel': u'execute'}
        #   ]
        redirect = [
            link
            for link in r_content_as_dict["links"]
            if link["rel"].lower() == "approval_url"
        ][0]["href"]
        parsed_redirect = urlparse(redirect)
        token = parse_qs(parsed_redirect.query)["token"][0]
        response = {
            "status": Donation.AWAITING_PAYMENT,
            "payment_id": r_content_as_dict.get("id"),
            "transaction_id": token,
            "redirect": redirect,
        }
        logger.info("Created payment in paypal with response: %s", response)
        return response
    else:
        raise PaymentFailureException("UNABLE_TO_MAKE_PAYMENT")


def donate_paypal_cancel(request: HttpRequest) -> HttpResponse:
    d = Donation.objects.get(transaction_id=request.GET["token"])
    d.status = Donation.CANCELLED
    d.save()

    return render(
        request,
        "donate_complete.html",
        {"error": "user_cancelled", "private": True},
    )
