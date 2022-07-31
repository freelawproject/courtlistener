from django.urls import path, re_path

from cl.alerts.views import (
    delete_alert,
    delete_alert_confirm,
    disable_alert,
    edit_alert_redirect,
    enable_alert,
    new_docket_alert,
    toggle_docket_alert,
    toggle_docket_alert_confirmation,
)

urlpatterns = [
    path("alert/edit/<int:pk>/", edit_alert_redirect),
    path("alert/delete/<int:pk>/", delete_alert),
    path(
        "alert/delete/confirm/<int:pk>/",
        delete_alert_confirm,
        name="delete_alert_confirm",
    ),
    re_path(
        "alert/disable/([a-zA-Z0-9]{40})/",
        disable_alert,
        name="disable_alert",
    ),
    re_path(
        r"^alert/enable/([a-zA-Z0-9]{40})/$", enable_alert, name="enable_alert"
    ),
    path(
        "alert/docket/toggle/",
        toggle_docket_alert,
        name="toggle_docket_alert",
    ),
    path("alert/docket/new/", new_docket_alert, name="new_docket_alert"),
    re_path(
        "alert/docket/(unsubscribe|subscribe)/([a-zA-Z0-9]{40})/",
        toggle_docket_alert_confirmation,
        name="toggle_docket_alert_confirmation",
    ),
]
