"""Django admin configuration for donations, memberships, and Neon webhook events."""

from django.contrib import admin

from cl.donate.models import (
    Donation,
    MonthlyDonation,
    NeonMembership,
    NeonWebhookEvent,
)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    """Admin for donations."""

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
    """Inline for editing donations on a parent object's admin page."""

    model = Donation
    extra = 0


@admin.register(MonthlyDonation)
class MonthlyDonationAdmin(admin.ModelAdmin):
    """Admin for monthly donations."""

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
    """Inline for editing monthly donations on a parent object's admin page."""

    model = MonthlyDonation
    extra = 0


class NeonMembershipInline(admin.StackedInline):
    """Inline for editing Neon memberships on a parent object's admin page."""

    model = NeonMembership
    extra = 0


@admin.register(NeonWebhookEvent)
class NeonWebhookEventAdmin(admin.ModelAdmin):
    """Admin for Neon webhook events."""

    list_display = (
        "id",
        "get_trigger",
        "account_id",
        "membership_id",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )

    @admin.display(description="Trigger")
    def get_trigger(self, obj):
        """Display the event's trigger."""
        return obj.get_trigger_display()
