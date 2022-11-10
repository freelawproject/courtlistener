from django.shortcuts import render
from django.template import loader
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED
from rest_framework.viewsets import ModelViewSet

from cl.api.api_permissions import IsOwner
from cl.api.models import Webhook, WebhookEventType
from cl.api.tasks import send_test_webhook_event
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
            status=status.HTTP_204_NO_CONTENT,
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
                status=HTTP_201_CREATED,
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
                status=HTTP_200_OK,
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
        da_dummy_content = ""
        da_dummy_curl = ""
        match event_type:
            case WebhookEventType.DOCKET_ALERT:
                da_template = loader.get_template(
                    "includes/docket_alert_webhook_dummy.txt"
                )
                da_dummy_content = da_template.render().strip()
                da_curl_template = loader.get_template(
                    "includes/docket_alert_webhook_dummy_curl.txt"
                )
                da_dummy_curl = da_curl_template.render(
                    {"endpoint_url": webhook.url}
                ).strip()
            case WebhookEventType.SEARCH_ALERT:
                # Currently, we don't yet support search alert webhooks.
                da_dummy_content = (
                    "Currently, we don't yet support "
                    f"{WebhookEventType.SEARCH_ALERT.label} webhooks."
                )
                da_dummy_curl = (
                    "Currently, we don't yet support "
                    f"{WebhookEventType.SEARCH_ALERT.label} webhooks."
                )
            case WebhookEventType.RECAP_FETCH:
                # Currently, we don't yet support recap fetch webhooks.
                da_dummy_content = (
                    "Currently, we don't yet support "
                    f"{WebhookEventType.RECAP_FETCH.label} webhooks."
                )
                da_dummy_curl = (
                    "Currently, we don't yet support "
                    f"{WebhookEventType.RECAP_FETCH.label} webhooks."
                )

        if self.request.method == "GET":
            return Response(
                {
                    "webhook": webhook,
                    "dummy_content": da_dummy_content,
                    "dummy_curl": da_dummy_curl,
                    "da_type": WebhookEventType.DOCKET_ALERT,
                },
                template_name="includes/webhooks_htmx/webhooks-test-webhook.html",
            )

        # On POST send the webhook test event.
        send_test_webhook_event.delay(webhook.pk, da_dummy_content)
        return Response(
            status=HTTP_200_OK,
        )
