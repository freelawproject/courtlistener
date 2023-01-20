from django.urls import path

from cl.favorites.views import (
    delete_note,
    save_or_update_note,
    view_tag,
    view_tags,
)

urlpatterns = [
    # Notes pages
    path(
        "notes/create-or-update/",
        save_or_update_note,
        name="save_or_update_note",
    ),
    path("notes/delete/", delete_note, name="delete_note"),
    # Tag pages
    path(
        "tags/<str:username>/<slug:tag_name>/",
        view_tag,
        name="view_tag",
    ),
    path("tags/<str:username>/", view_tags, name="tag_list"),
]
