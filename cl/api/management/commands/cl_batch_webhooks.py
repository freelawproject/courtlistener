from cl.api.models import WebhookEventType
from cl.api.tasks import (
    consume_webhook_event_batch,
    send_opinion_clusters_created_webhook,
    send_opinion_clusters_deleted_webhook,
    send_opinion_clusters_updated_webhook,
    send_opinions_created_webhook,
    send_opinions_deleted_webhook,
    send_opinions_updated_webhook,
)
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    """Command to run a loop to batch webhooks."""

    help = "Execute batched webhooks."

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        self.stdout.write("Starting webhook event batching loops", ending="")

        # Start the batch consumer for the webhook event queue
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_CLUSTER_CREATE,
                send_opinion_clusters_created_webhook,
            ]
        )
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_CLUSTER_UPDATE,
                send_opinion_clusters_updated_webhook,
            ]
        )
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_CLUSTER_DELETE,
                send_opinion_clusters_deleted_webhook,
            ]
        )
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_CREATE,
                send_opinions_created_webhook,
            ]
        )
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_UPDATE,
                send_opinions_updated_webhook,
            ]
        )
        consume_webhook_event_batch.apply_async(
            args=[
                WebhookEventType.OPINION_DELETE,
                send_opinions_deleted_webhook,
            ]
        )

        self.stdout.write("Event batching loops registered", ending="")
