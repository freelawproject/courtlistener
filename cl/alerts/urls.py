from django.conf.urls import url
from cl.alerts.views import (
    delete_alert,
    delete_alert_confirm,
    edit_alert_redirect,
)

urlpatterns = [
    url(r'^alert/edit/(\d{1,6})/$', edit_alert_redirect),
    url(r'^alert/delete/(\d{1,6})/$', delete_alert),
    url(r'^alert/delete/confirm/(\d{1,6})/$', delete_alert_confirm),
]
