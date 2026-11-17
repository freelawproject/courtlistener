"""Django admin configuration for notes, tags, prayers, and generic counts."""

from django.contrib import admin

from cl.favorites.models import (
    DocketTag,
    GenericCount,
    Note,
    Prayer,
    PrayerAvailability,
    UserTag,
)


class NoteInline(admin.TabularInline):
    """Inline for editing notes on a parent object's admin page."""

    model = Note
    extra = 1
    raw_id_fields = (
        "user",
        "content_type",
    )


class PrayerInline(admin.TabularInline):
    """Inline for editing prayers on a parent object's admin page."""

    model = Prayer
    raw_id_fields = ("recap_document",)
    extra = 1


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    """Admin for notes."""

    list_display = (
        "id",
        "user",
        "content_type",
        "object_id",
    )
    raw_id_fields = (
        "user",
        "content_type",
    )


@admin.register(DocketTag)
class DocketTagAdmin(admin.ModelAdmin):
    """Admin for tags applied to dockets."""

    raw_id_fields = ("docket", "tag")
    list_display = (
        "id",
        "tag",
    )


@admin.register(UserTag)
class UserTagAdmin(admin.ModelAdmin):
    """Admin for users' tags."""

    raw_id_fields = ("user", "dockets")
    readonly_fields = ("date_modified", "date_created")


class UserTagInline(admin.StackedInline):
    """Inline for editing users' tags on a parent object's admin page."""

    model = UserTag
    extra = 0


@admin.register(Prayer)
class PrayerAdmin(admin.ModelAdmin):
    """Admin for prayers."""

    raw_id_fields = ("user", "recap_document")
    readonly_fields = ("date_created",)
    list_display = (
        "id",
        "user",
        "recap_document",
    )


@admin.register(PrayerAvailability)
class PrayerAvailabilityAdmin(admin.ModelAdmin):
    """Admin for prayer availability records."""

    raw_id_fields = ("recap_document",)
    list_display = (
        "id",
        "recap_document",
        "last_checked",
    )


@admin.register(GenericCount)
class GenericCountAdmin(admin.ModelAdmin):
    """Admin for generic counts, searchable by label prefix."""

    search_fields = ("label__startswith",)
