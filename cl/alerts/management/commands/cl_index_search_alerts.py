from cl.alerts.models import Alert
from cl.alerts.utils import index_alert_document
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.documents import AudioPercolator
from cl.search.models import SEARCH_TYPES


class Command(VerboseCommand):
    help = "Index existing Alert objects into Elasticsearch Percolator index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The Alert pk to start indexing from.",
        )
        parser.add_argument(
            "--alert-type",
            required=True,
            choices=SEARCH_TYPES.ALL_TYPES,
            help=f"The Search Alert query type to index ({', '.join(SEARCH_TYPES.ALL_TYPES)})",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        pk_offset = options["pk_offset"]
        alert_type = options["alert_type"]

        # Filter Alert objects by pk_offset and query alert type to index.
        queryset = (
            Alert.objects.filter(
                pk__gte=pk_offset, query__icontains=f"type={alert_type}"
            )
            .only("pk", "rate", "query")
            .order_by("pk")
        )

        if alert_type == SEARCH_TYPES.ORAL_ARGUMENT:
            es_document = AudioPercolator
        else:
            logger.info(
                f"'{alert_type}' Alert type indexing is not supported yet."
            )
            return

        indexing_counter = 0
        # Indexing the Alert objects
        for alert in queryset.iterator():
            logger.info(f"Indexing Alert with ID: {alert.pk}")
            indexed = index_alert_document(alert, es_document)
            if not indexed:
                logger.warning(f"Error indexing Alert ID: {alert.pk}")
                continue
            indexing_counter += 1

        self.stdout.write(
            f"Successfully indexed {indexing_counter} alerts of type "
            f"{alert_type} from pk {pk_offset}."
        )
