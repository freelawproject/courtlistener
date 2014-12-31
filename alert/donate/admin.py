from django.contrib import admin
from alert.donate.models import Donation
from alert.userHandling.models import UserProfile


class DonorInline(admin.TabularInline):
    model = UserProfile.donation.through
    max_num = 1
    raw_id_fields = (
        'userprofile',
    )


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
    )
    list_filter = (
        'payment_provider',
        'status',
    )
    inlines = (
        DonorInline,
    )


admin.site.register(Donation, DonationAdmin)
