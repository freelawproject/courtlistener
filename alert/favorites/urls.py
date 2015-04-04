from django.conf.urls import patterns
from alert.favorites.views import save_or_update_favorite, delete_favorite

urlpatterns = patterns('',
    # Favorites pages
    (r'^favorite/create-or-update/$', save_or_update_favorite),
    (r'^favorite/delete/$', delete_favorite),
)
