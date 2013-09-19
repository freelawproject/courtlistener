from datetime import datetime
import hashlib
import hmac
import logging
import simplejson
import requests
from alert.donate.models import Donation
from django.conf import settings
from django.http import HttpResponseNotAllowed, HttpResponse, HttpResponseForbidden
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def check_dwolla_signature(proposed_signature, raw):
    signature = hmac.new(settings.DWOLLA_SECRET_KEY, raw, hashlib.sha1).hexdigest()
    return True if (signature == proposed_signature) else False


@csrf_exempt
def process_dwolla_callback(request):
    if request.method == 'POST':
        data = simplejson.loads(request.raw_post_data)  # Update for Django 1.4 to request.body
        logger.info('data is: %s' % data)
        if check_dwolla_signature(data['Signature'], '%s&%s' % (data['CheckoutId'], data['Amount'])):
            d = Donation.objects.get(payment_id=data['CheckoutId'])
            if data['Status'].lower() == 'completed':
                d.amount = data['amount']
                d.status = 2
                from alert.donate.views import send_thank_you_email
                send_thank_you_email(d)
            elif data['Status'].lower() == 'failed':
                d.status = 1
            d.save()
            return HttpResponse('<h1>200: OK</h1>')
        else:
            return HttpResponseForbidden('<h1>403: Did not pass signature check.</h1>')
    else:
        return HttpResponseNotAllowed('<h1>405: This is a callback endpoint for a payment provider. Only POST methods '
                                      'are allowed.</h1>')


@csrf_exempt
def process_dwolla_transaction_status_callback(request):
    if request.method == 'POST':
        data = simplejson.loads(request.raw_post_data)  # Update for django 1.4 to request.body
        if check_dwolla_signature(request.META['X-Dwolla-Signature'], request.raw_post_data):
            d = Donation.objects.get(payment_id=data['Id'])
            if data['Value'].lower() == 'processed':
                d.clearing_date = datetime.strptime(data['Triggered'], '%m/%d/%Y %I:%M:%S %p')
                d.status = 4
            elif data['Value'].lower() == 'pending':
                d.status = 5
            elif data['Value'].lower() == 'cancelled':
                d.status = 3
            elif data['Value'].lower() == 'failed':
                d.status = 6
            elif data['Value'].lower() == 'reclaimed':
                d.status = 7
            d.save()
            return HttpResponse('<h1>200: OK</h1>')
        else:
            return HttpResponseForbidden('<h1>403: Did not pass signature check.</h1>')
    else:
        return HttpResponseNotAllowed('<h1>405: This is a callback endpoint for a payment provider. Only POST methods '
                                      'are allowed.</h1>')


def process_dwolla_payment(cd_donation_form, cd_profile_form, cd_user_form, test=settings.PAYMENT_TESTING_MODE):
    """Generate a redirect URL for the user, and shuttle them off"""
    data = {
        'key': settings.DWOLLA_APPLICATION_KEY,
        'secret': settings.DWOLLA_SECRET_KEY,
        'callback': settings.DWOLLA_CALLBACK,
        'redirect': settings.DWOLLA_REDIRECT,
        'allowFundingSources': True,
        'test': test,
        'purchaseOrder': {
            'customerInfo': {
                'firstName': cd_user_form['first_name'],
                'lastName': cd_user_form['last_name'],
                'email': cd_user_form['email'],
                'city': cd_profile_form['city'],
                'state': cd_profile_form['state'],
                'zip': cd_profile_form['zip_code'],
            },
            'DestinationID': settings.DWOLLA_ACCOUNT_ID,
            'shipping': '0',
            'tax': '0',
            'total': cd_donation_form['amount'],
            'OrderItems': [
                {
                    'Name': 'Donation to the Free Law Project',
                    'Description': 'Your donation makes our work possible.',
                    'Price': cd_donation_form['amount'],
                    'Quantity': '1',
                },
            ]
        }
    }
    r = requests.post(
        'https://www.dwolla.com/payment/request',
        data=simplejson.dumps(data),
        headers={'Content-Type': 'application/json'}
    )
    r_content_as_dict = simplejson.loads(r.content)
    response = {
        'result': r_content_as_dict.get('Result'),
        'status_code': r.status_code,
        'message': r_content_as_dict.get('Message'),
        'redirect': 'https://www.dwolla.com/payment/checkout/%s' % r_content_as_dict.get('CheckoutId'),
        'payment_id': r_content_as_dict.get('CheckoutId')
    }
    return response


def donate_dwolla_complete(request):
    logger.info('Dwolla complete.')
    if len(request.GET) > 0:
        # We've gotten some information from the payment provider
        if request.GET.get('error') == 'failure' and request.GET.get('error_description') == 'User Cancelled':
            # Cancelled order.
            return render_to_response(
                'donate/donate_complete.html',
                {
                    'error': 'User Cancelled',
                    'private': True,
                },
                RequestContext(request),
            )

    return render_to_response(
        'donate/donate_complete.html',
        {
            'error': "None",
            'private': True,
        },
        RequestContext(request)
    )
