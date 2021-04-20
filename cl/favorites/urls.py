from django.conf.urls import url
from django.urls import path

from cl.favorites.views import (
    delete_favorite,
    save_or_update_favorite,
    view_tag,
    view_tags,
)

urlpatterns = [
    # Favorites pages
    path(
        "favorite/create-or-update/",
        save_or_update_favorite,
        name="save_or_update_favorite",
    ),
    path("favorite/delete/", delete_favorite, name="delete_favorite"),
    # Tag pages
    path(
        "tags/<str:username>/<slug:tag_name>/",
        view_tag,
        name="view_tag",
    ),
    url(r"^tags/(?P<username>[^/]*)", view_tags, name="tag_list"),
]
