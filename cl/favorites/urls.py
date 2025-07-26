from django.urls import path

from cl.favorites import views

urlpatterns = [
    # Notes pages
    path(
        "notes/create-or-update/",
        views.save_or_update_note,
        name="save_or_update_note",
    ),
    path("notes/delete/", views.delete_note, name="delete_note"),
    # Tag pages
    path(
        "tags/<str:username>/<slug:tag_name>/",
        views.view_tag,
        name="view_tag",
    ),
    path("tags/<str:username>/", views.view_tags, name="tag_list"),
    # Prayer pages
    path("prayers/top/", views.open_prayers, name="top_prayers"),
    path(
        "prayer/create/<int:recap_document>/",
        views.create_prayer_view,
        name="create_prayer",
    ),
    path(
        "prayer/delete/<int:recap_document>/",
        views.delete_prayer_view,
        name="delete_prayer",
    ),
    path(
        "prayers/<str:username>/", views.user_prayers_view, name="user_prayers"
    ),
    path(
        "prayers/<str:username>/granted",
        views.user_prayers_view_granted,
        name="user_prayers_granted",
    ),
    path(
        "prayers/pending/toggle/",
        views.toggle_prayer_public,
        name="toggle_prayer_public",
    ),
]
