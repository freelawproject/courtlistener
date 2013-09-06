from datetime import datetime
import hashlib
import hmac
import json
import requests
from alert.donate.models import Donation
from django.conf import settings
from django.http import HttpResponseNotAllowed


def check_dwolla_signature(proposed_signature, checkout_id, amount):
    # From Dwolla documentation
    raw = '%s&%s' % (checkout_id, amount)
    signature = hmac.new(settings.DWOLLA_SECRET_KEY, raw, hashlib.sha1).hexdigest()
    return True if (signature == proposed_signature) else False


def process_dwolla_callback(request):
    if request.method == 'POST':
        data = json.loads(request.raw_post_data)  # Update for Django 1.4 to request.body
        if check_dwolla_signature(data['Signature'], data['CheckoutId'], data['amount']):
            d = Donation.objects.get(payment_id=data['CheckoutId'])
            if data['Status'] == 'Completed':
                d.amount = data['amount']
                d.clearing_date = datetime.strptime(data['ClearingDate'], '%m/%d/%Y %I:%M:%S %p')
                d.status = 'SUCCESSFUL_COMPLETION'
                d.save()
                from alert.donate.views import send_thank_you_email
                send_thank_you_email(d)
            elif data['Status'] == 'Failed':
                d.status = 'ERROR'
                d.save()
    else:
        return HttpResponseNotAllowed('<h1>405: This is a callback endpoint for a payment provider. Only POST methods '
                                      'are allowed.</h1>')


def process_stripe_payment(cd_donation_form, cd_profile_form, cd_user_form, test=True):
    """Generate a redirect URL for the user, and shuttle them off"""
    data = {
        'key': settings.DWOLLA_APPLICATION_KEY,
        'secret': settings.DWOLLA_SECRET_KEY,
        'callback': settings.DWOLLA_CALLLBACK,
        'redirect': settings.PAYMENT_REDIRECT,
        'allowFundingSources': True,
        'test': test,
        'purchaseOrder': {
            'customerInfo': {
                'firstName': cd_user_form['first'],
                'lastName': cd_user_form['last'],
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
    r = requests.POST(
        'https://www.dwolla.com/payment/request',
        data=json.dumps(data),
        headers={'Content-Type': 'application/json'}
    )
    r_content_as_dict = json.loads(r.content)
    response = {
        'result': r_content_as_dict.get('Result'),
        'status_code': r.status_code,
        'message': r_content_as_dict.get('Message'),
        'redirect': 'https://www.dwolla.com/payment/checkout/%s' % r_content_as_dict.get('CheckoutId'),
        'payment_id': r_content_as_dict.get('CheckoutId')
    }
    return response
