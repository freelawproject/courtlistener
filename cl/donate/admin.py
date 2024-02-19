from django.contrib import admin

from cl.donate.models import (
    Donation,
    MonthlyDonation,
    NeonMembership,
    NeonWebhookEvent,
)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_modified",
        "date_created",
    )
    list_display = (
        "__str__",
        "amount",
        "payment_provider",
        "status",
        "date_created",
        "referrer",
    )
    list_filter = (
        "payment_provider",
        "status",
        "referrer",
    )
    raw_id_fields = ("donor",)


class DonationInline(admin.StackedInline):
    model = Donation
    extra = 0


@admin.register(MonthlyDonation)
class MonthlyDonationAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_display = (
        "__str__",
        "donor_id",
        "enabled",
        "monthly_donation_amount",
        "failure_count",
        "monthly_donation_day",
    )
    list_filter = (
        "enabled",
        "failure_count",
        "monthly_donation_day",
    )
    raw_id_fields = ("donor",)


class MonthlyDonationInline(admin.TabularInline):
    model = MonthlyDonation
    extra = 0


class NeonMembershipInline(admin.StackedInline):
    model = NeonMembership
    extra = 0


@admin.register(NeonWebhookEvent)
class NeonWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_trigger",
        "account_id",
        "membership_id",
    )

    @admin.display(description="Trigger")
    def get_trigger(self, obj):
        return obj.get_trigger_display()
