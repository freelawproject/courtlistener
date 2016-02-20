from django.contrib import admin
from cl.favorites.models import Favorite


class FavoriteInline(admin.TabularInline):
    model = Favorite
    extra = 1
    raw_id_fields = (
        'user',
        "cluster_id",
        "audio_id",
    )
