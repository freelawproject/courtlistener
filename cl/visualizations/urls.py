from django.conf.urls import url
from cl.visualizations.views import (
    view_visualization,
    new_visualization,
    edit_visualization,
    delete_visualization,
    mapper_homepage,
    view_embedded_visualization)

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
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/edit/$',
        edit_visualization,
        name='edit_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/delete/$',
        delete_visualization,
        name='delete_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/embed/$',
        view_embedded_visualization,
        name='view_embedded_visualization',
    ),
    url(
        r'^visualizations/scotus-mapper/(?P<pk>\d*)/(?P<slug>[^/]*)/$',
        view_visualization,
        name='view_visualization',
    ),
]
