from alert.alerts.views import delete_alert, delete_alert_confirm, \
    edit_alert_redirect
from django.conf.urls import patterns

urlpatterns = patterns('',
    # Alert pages
    (r'^alert/edit/(\d{1,6})/$', edit_alert_redirect),
    (r'^alert/delete/(\d{1,6})/$', delete_alert),
    (r'^alert/delete/confirm/(\d{1,6})/$', delete_alert_confirm),
)
