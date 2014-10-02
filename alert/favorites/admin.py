from django.contrib import admin
from alert.favorites.models import Favorite


class FavoriteAdmin(admin.ModelAdmin):
    raw_id_fields = ("doc_id", "audio_id")

admin.site.register(Favorite, FavoriteAdmin)
