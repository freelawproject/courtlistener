from django.conf.urls import url

from cl.favorites.views import (
    delete_favorite,
    save_or_update_favorite,
    view_tag,
)

urlpatterns = [
    # Favorites pages
    url(
        r"^favorite/create-or-update/$",
        save_or_update_favorite,
        name="save_or_update_favorite",
    ),
    url(r"^favorite/delete/$", delete_favorite, name="delete_favorite"),
    # Tag pages
    url(
        r"^tags/(?P<username>[^/]*)/(?P<tag_name>[^/]*)/",
        view_tag,
        name="view_tag",
    ),
]
