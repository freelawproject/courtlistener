from django.conf.urls import url

from cl.alerts.views import (
    delete_alert,
    delete_alert_confirm,
    disable_alert,
    edit_alert_redirect,
    enable_alert,
    toggle_docket_alert,
)

urlpatterns = [
    url(r'^alert/edit/(\d{1,6})/$', edit_alert_redirect),
    url(r'^alert/delete/(\d{1,6})/$', delete_alert),
    url(r'^alert/delete/confirm/(\d{1,6})/$', delete_alert_confirm),
    url(r'^alert/disable/([a-zA-Z0-9]{40})/$', disable_alert, name='disable_alert'),
    url(r'^alert/enable/([a-zA-Z0-9]{40})/$', enable_alert, name='enable_alert'),
    url(r'^alert/docket/toggle/$', toggle_docket_alert,
        name="toggle_docket_alert"),
]
