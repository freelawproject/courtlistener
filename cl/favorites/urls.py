from django.conf.urls import url
from cl.favorites.views import save_or_update_favorite, delete_favorite

urlpatterns = [
    # Favorites pages
    url(r'^favorite/create-or-update/$', save_or_update_favorite),
    url(r'^favorite/delete/$', delete_favorite),
]
