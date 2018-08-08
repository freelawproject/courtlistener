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


admin.site.register(MonthlyDonation)
