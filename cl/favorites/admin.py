from django.contrib import admin

from cl.favorites.models import DocketTag, Favorite, UserTag


class FavoriteInline(admin.TabularInline):
    model = Favorite
    extra = 1
    raw_id_fields = (
        "user",
        "cluster_id",
        "audio_id",
        "docket_id",
        "recap_doc_id",
    )


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
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
    raw_id_fields = (
        "docket",
    )
    list_display = (
        "id",
        "tag",
    )


admin.site.register(UserTag)
