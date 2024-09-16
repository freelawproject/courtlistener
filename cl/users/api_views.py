from http import HTTPStatus

from django.core.paginator import Paginator
from django.shortcuts import render
from django.template import loader
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from cl.api.api_permissions import IsOwner
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.tasks import send_test_webhook_event
from cl.users.filters import WebhookEventViewFilter
from cl.users.forms import WebhookForm


class WebhooksViewSet(ModelViewSet):
    """
    A set of actions to handle the listing, creation, deleting, and updating
    of webhooks for htmx.
    """

    permission_classes = [IsAuthenticated, IsOwner]
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]

    def get_queryset(self):
        """
        Return a list of all the webhooks
        for the currently authenticated user.
        """
        user = self.request.user
        return Webhook.objects.filter(user=user).order_by("date_created")

    def list(self, request, *args, **kwargs):
        webhooks = self.get_queryset()
        return Response(
            {"webhooks": webhooks},
            template_name="includes/webhooks_htmx/webhooks-list.html",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            status=HTTPStatus.NO_CONTENT,
            headers={"HX-Trigger": "webhooksListChanged"},
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        update = True
        form = WebhookForm(update, request.user, instance=instance)
        return Response(
            {"webhook_form": form, "webhook_id": instance.pk},
            template_name="includes/webhooks_htmx/webhooks-form-update.html",
        )

    def create(self, request, *args, **kwargs):
        update = False
        webhook = Webhook()
        form = WebhookForm(
            update, request.user, request.POST, instance=webhook
        )
        if form.is_valid():
            webhook.user = request.user
            form.save()
            return Response(
                status=HTTPStatus.CREATED,
                headers={"HX-Trigger": "webhooksListChanged"},
            )
        else:
            return render(
                request,
                "includes/webhooks_htmx/webhooks-form-create.html",
                {"webhook_form": form},
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        update = True
        form = WebhookForm(
            update, request.user, request.POST, instance=instance
        )
        if form.is_valid():
            instance.user = request.user
            form.save()
            return Response(
                status=HTTPStatus.OK,
                headers={"HX-Trigger": "webhooksListChanged"},
            )
        else:
            return render(
                request,
                "includes/webhooks_htmx/webhooks-form-update.html",
                {"webhook_form": form, "webhook_id": instance.pk},
            )

    @action(detail=False, methods=["get"])
    def render_form(self, request, *args, **kwargs):
        webhook = Webhook()
        update = False
        form = WebhookForm(update, request.user, instance=webhook)
        return Response(
            {"webhook_form": form},
            template_name="includes/webhooks_htmx/webhooks-form-create.html",
        )

    @action(detail=True, methods=["get", "post"])
    def test_webhook(self, request, *args, **kwargs):
        """Render the webhook test template on GET and send the test webhook
        event on POST.
        """

        webhook = self.get_object()
        event_type = webhook.event_type
        match event_type:
            case WebhookEventType.DOCKET_ALERT:
                event_template = loader.get_template(
                    "includes/docket_alert_webhook_dummy.txt"
                )
                event_dummy_content = event_template.render().strip()
                event_curl_template = loader.get_template(
                    "includes/docket_alert_webhook_dummy_curl.txt"
                )
                event_dummy_curl = event_curl_template.render(
                    {"endpoint_url": webhook.url}
                ).strip()
            case WebhookEventType.SEARCH_ALERT:
                event_template = loader.get_template(
                    "includes/search_alert_webhook_dummy.txt"
                )
                event_dummy_content = event_template.render().strip()
                event_curl_template = loader.get_template(
                    "includes/search_alert_webhook_dummy_curl.txt"
                )
                event_dummy_curl = event_curl_template.render(
                    {"endpoint_url": webhook.url}
                ).strip()
            case WebhookEventType.OLD_DOCKET_ALERTS_REPORT:
                event_template = loader.get_template(
                    "includes/old_alerts_report_webhook_dummy.txt"
                )
                event_dummy_content = event_template.render().strip()
                event_curl_template = loader.get_template(
                    "includes/old_alerts_report_webhook_dummy_curl.txt"
                )
                event_dummy_curl = event_curl_template.render(
                    {"endpoint_url": webhook.url}
                ).strip()
            case WebhookEventType.RECAP_FETCH:
                event_template = loader.get_template(
                    "includes/recap_fetch_webhook_dummy.txt"
                )
                event_dummy_content = event_template.render().strip()
                event_curl_template = loader.get_template(
                    "includes/recap_fetch_webhook_dummy_curl.txt"
                )
                event_dummy_curl = event_curl_template.render(
                    {"endpoint_url": webhook.url}
                ).strip()
            case _:
                # Webhook types with no support yet.
                event_dummy_content = (
                    "Currently, we don't yet support events for this type of "
                    "webhook."
                )
                event_dummy_curl = (
                    "Currently, we don't yet support events for this type of "
                    "webhook."
                )

        if self.request.method == "GET":
            return Response(
                {
                    "webhook": webhook,
                    "dummy_content": event_dummy_content,
                    "dummy_curl": event_dummy_curl,
                    "event_types": [
                        WebhookEventType.DOCKET_ALERT,
                        WebhookEventType.SEARCH_ALERT,
                        WebhookEventType.OLD_DOCKET_ALERTS_REPORT,
                        WebhookEventType.RECAP_FETCH,
                    ],
                },
                template_name="includes/webhooks_htmx/webhooks-test-webhook.html",
            )

        # On POST enqueue the webhook test event.
        send_test_webhook_event.delay(webhook.pk, event_dummy_content)
        return Response(
            status=HTTPStatus.OK,
        )


class WebhookEventViewSet(ModelViewSet):
    """
    A set of actions to handle listing and filtering webhooks events for htmx.
    """

    permission_classes = [IsAuthenticated, IsOwner]
    renderer_classes = [TemplateHTMLRenderer]
    filterset_class = WebhookEventViewFilter

    def get_queryset(self):
        """
        Returns a list of all webhook events for the currently authenticated
        user.
        """
        user = self.request.user
        return WebhookEvent.objects.filter(webhook__user=user).order_by(
            "-date_created"
        )

    def list(self, request, *args, **kwargs):
        webhook_events = self.filter_queryset(self.get_queryset())
        page_number = self.request.query_params.get("page")
        paginator = Paginator(webhook_events, 20)
        results = paginator.get_page(page_number)

        debug = self.request.query_params.get("debug", "")
        type_filter = self.request.query_params.get("webhook__event_type", "")
        status_filter = self.request.query_params.get("event_status", "")

        return Response(
            {
                "results": results,
                "type_filter": type_filter,
                "status_filter": status_filter,
                "debug": debug,
                "webhooks": True,
            },
            template_name="includes/webhooks_htmx/webhook-logs-list.html",
        )
