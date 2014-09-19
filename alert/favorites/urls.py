from django.conf.urls import patterns
from alert.favorites.views import save_or_update_favorite, delete_favorite, \
    edit_favorite

urlpatterns = patterns('',
    # Favorites pages
    (r'^favorite/create-or-update/$', save_or_update_favorite),
    (r'^favorite/delete/$', delete_favorite),
    (r'^favorite/edit/(\d{1,6})/$', edit_favorite),
)
