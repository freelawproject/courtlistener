from django.contrib import admin

from cl.favorites.models import (
    DocketTag,
    Note,
    Prayer,
    PrayerAvailability,
    UserTag,
)


class NoteInline(admin.TabularInline):
    model = Note
    extra = 1
    raw_id_fields = (
        "user",
        "cluster_id",
        "audio_id",
        "docket_id",
        "recap_doc_id",
    )


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "cluster_id",
    )
    raw_id_fields = (
        "user",
        "cluster_id",
        "audio_id",
        "docket_id",
        "recap_doc_id",
    )


@admin.register(DocketTag)
class DocketTagAdmin(admin.ModelAdmin):
    raw_id_fields = ("docket", "tag")
    list_display = (
        "id",
        "tag",
    )


@admin.register(UserTag)
class UserTagAdmin(admin.ModelAdmin):
    raw_id_fields = ("user", "dockets")
    readonly_fields = ("date_modified", "date_created")


class UserTagInline(admin.StackedInline):
    model = UserTag
    extra = 0


@admin.register(Prayer)
class PrayerAdmin(admin.ModelAdmin):
    raw_id_fields = ("user", "recap_document")
    readonly_fields = ("date_created",)
    list_display = (
        "id",
        "user",
        "recap_document",
    )


@admin.register(PrayerAvailability)
class PrayerAvailabilityAdmin(admin.ModelAdmin):
    raw_id_fields = ("recap_document",)
    list_display = (
        "id",
        "recap_document",
        "last_checked",
    )
