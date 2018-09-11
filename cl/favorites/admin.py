from django.contrib import admin

from cl.favorites.models import Favorite


class FavoriteInline(admin.TabularInline):
    model = Favorite
    extra = 1
    raw_id_fields = (
        'user',
        "cluster_id",
        "audio_id",
        "docket_id",
        "recap_doc_id",
    )


class FavoriteAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'cluster_id',
    )
    raw_id_fields = (
        'user',
        'cluster_id',
    )


admin.site.register(Favorite, FavoriteAdmin)
