from django.conf.urls import url
from cl.visualizations.views import (
    view_visualization,
    mapper_homepage,
    new_visualization,
    visualization_profile_page,
)

urlpatterns = [
    url(
        r'^visualizations/scotus-mapper/$',
        mapper_homepage,
        name='mapper_homepage',
    ),
    url(
        r'^visualizations/scotus-mapper/new/$',
        new_visualization,
        name='new_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/(?P<slug>.*)/$',
        view_visualization,
        name='view_visualization',
    ),
    url(
        r'^profile/visualizations/$',
        visualization_profile_page,
        name="visualization_profile_page",
    ),
]
