from django.urls import path

from cl.favorites.views import (
    create_prayer_view,
    delete_note,
    delete_prayer_view,
    open_prayers,
    save_or_update_note,
    user_prayers_view,
    user_prayers_view_granted,
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
    # Prayer pages
    path("prayers/top/", open_prayers, name="top_prayers"),
    path(
        "prayer/create/<int:recap_document>/",
        create_prayer_view,
        name="create_prayer",
    ),
    path(
        "prayer/delete/<int:recap_document>/",
        delete_prayer_view,
        name="delete_prayer",
    ),
    path("prayers/<str:username>/", user_prayers_view, name="user_prayers"),
    path(
        "prayers/<str:username>/granted",
        user_prayers_view_granted,
        name="user_prayers_granted",
    ),
]
