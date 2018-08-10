from django.contrib import admin

from cl.donate.models import Donation, MonthlyDonation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    readonly_fields = (
        'date_modified',
        'date_created',
    )
    list_display = (
        '__str__',
        'amount',
        'payment_provider',
        'status',
        'date_created',
        'referrer',
    )
    list_filter = (
        'payment_provider',
        'status',
        'referrer',
    )
    raw_id_fields = (
        'donor',
    )


@admin.register(MonthlyDonation)
class MonthlyDonationAdmin(admin.ModelAdmin):
    readonly_fields = (
        'date_created',
        'date_modified',
    )
    list_display = (
        '__str__',
        'donor_id',
        'enabled',
        'monthly_donation_amount',
        'failure_count',
    )
    list_filter = (
        'enabled',
        'failure_count',
    )
    raw_id_fields = (
        'donor',
    )
