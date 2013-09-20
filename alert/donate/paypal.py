import json
import logging
import requests
from alert.donate.models import Donation
from datetime import datetime
from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from urlparse import urlparse, parse_qs

logger = logging.getLogger(__name__)


def get_paypal_access_token():
    """Get a token for the PayPal API.

    Query the PayPal API to get an access token. This could be improved by
    caching the token and detecting when it is expired.
    """
    logger.info("Got paypal token with value: ")
    r = requests.post(
        '%s/v1/oauth2/token' % settings.PAYPAL_ENDPOINT,
        headers={
            'Accept': 'application/json',
            'Accept-Language': 'en_US'
        },
        auth=(
            settings.PAYPAL_CLIENT_ID,
            settings.PAYPAL_SECRET_KEY,
        ),
        data={'grant_type': 'client_credentials'}
    )
    if r.status_code == 200:
        logger.info("Got paypal token successfully.")
    else:
        logger.warning("Problem getting paypal token status_code was: %s" % r.status_code)
    return json.loads(r.content).get('access_token')


@csrf_exempt
def process_paypal_callback(request):
    """Process the GET request that PayPal uses.

    After a transaction is completed, PayPal sends the user back to a page on our site. This could be our "Thanks" page,
    but since that page is seen by all the payment providers, instead this is an intermediate page, where we grab the
    correct things from the URL, process the item, and then shuttle the user off to the normal "Thanks" page.

    The other providers do this via a POST rather than a GET, so that's why this one is a bit of an oddball.
    """
    access_token = get_paypal_access_token()
    d = Donation.objects.get(transaction_id=request.GET['token'])
    r = request.post(
        '%s/v1/payments/payment/%s/execute/' % (settings.PAYPAL_ENDPOINT, d.payment_id),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % access_token
        },
        data={'payer_id': request.GET['PayerID']}
    )
    if r.status_code == 200:
        d.clearing_date = datetime.now()
        d.status = 'SUCCESSFUL_COMPLETION'
        d.save()
        from alert.donate.views import send_thank_you_email
        send_thank_you_email(d)
    else:
        d.status = 'ERROR'
        d.save()
    # Finally, show them the thank you page
    return HttpResponseRedirect('/donate/thanks/')


def process_paypal_payment(cd_donation_form):
    # https://developer.paypal.com/webapps/developer/docs/integration/web/accept-paypal-payment/
    access_token = get_paypal_access_token()
    if access_token:
        # We use it to set up a payment
        data = {
            'intent': 'sale',
            'redirect_urls': {
                'return_url': settings.PAYPAL_CALLBACK,
                'cancel_url': settings.PAYMENT_CANCELLATION,
            },
            'payer': {'payment_method': 'paypal'},
            'transactions': [
                {
                    'amount': {
                        'total': cd_donation_form['amount'],
                        'currency': 'USD',
                    },
                    'description': 'Donation to the Free Law Project',
                }
            ]
        }
        r = requests.post(
            '%s/v1/payments/payment' % settings.PAYPAL_ENDPOINT,
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer %s' % access_token
            },
            data=json.dumps(data)
        )

        if r.status_code == 201:  # "Created"
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
            redirect = [link for link in json.loads(r.content)['links'] if
                        link['rel'].lower() == 'approval_url'][0]['href']
            parsed_redirect = urlparse(redirect)
            token = parse_qs(parsed_redirect.query)['token']
            response = {
                'result': r_content_as_dict['state'],
                'status_code': r.status_code,
                'message': None,
                'redirect': redirect,
                'payment_id': r_content_as_dict.get('id'),
                'transaction_id': token
            }
            return response
        else:
            return {'result': 'UNABLE_TO_MAKE_PAYMENT'}
    else:
        return {'result': 'NO_ACCESS_TOKEN', }
