from django.db import models

FREQUENCY = (
    ('m', 'Monthly'),
    ('1', 'One time'),
)
PROVIDERS = (
    ('paypal', 'Paypal'),
    ('dwolla', 'Dwolla'),
    ('bitpay', 'BitPay'),
    ('stripe', 'Stripe'),
    ('check', 'Check'),
)


class Donation(models.Model):
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_index=True
    )
    email_address = models.EmailField(
        max_length=254  # According to Django docs.
    )
    frequency = models.CharField(
        choices=FREQUENCY,
        max_length=10
    )
    renew_annually = models.BooleanField(
        default=False,
    )
    amount = models.DecimalField(
        max_digits=9,
        decimal_places=2,
    )
    total = models.DecimalField(
        'For repeating donations, this is how much has been donated so far',
        max_digits=10,
        decimal_places=2,
    )
    currency = models.CharField(
        max_length=10,
    )
    payment_provider = models.CharField(
        max_length=50,
        choices=PROVIDERS,
    )
    referrer = models.TextField(
        'GET or HTTP referrer'
    )

    def __unicode__(self):
        if self.frequency == '1':
            repetition = 'does not repeat'
        elif self.frequency == 'a':
            repetition = 'repeats %s' % self.get_frequency_display()
        return '%s%s by %s that %s' % (self.amount, self.currency, self.email_address, repetition)
