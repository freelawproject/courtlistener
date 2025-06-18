from cl.alerts.models import Alert
from cl.alerts.tasks import es_save_alert_document
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.documents import AudioPercolator, RECAPPercolator, OpinionPercolator
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
        parser.add_argument(
            "--index-name",
            help="The ES target index name. If not provided, the default for "
            "the alert type will be used.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        pk_offset = options["pk_offset"]
        alert_type = options["alert_type"]
        index_name = options.get("index_name")

        alerts_types = (
            [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]
            if alert_type == SEARCH_TYPES.RECAP
            else [alert_type]
        )
        # Filter Alert objects by pk_offset and query alert type to index.
        queryset = (
            Alert.objects.filter(
                pk__gte=pk_offset, alert_type__in=alerts_types
            )
            .only("pk", "rate", "query")
            .order_by("pk")
        )

        match alert_type:
            case SEARCH_TYPES.ORAL_ARGUMENT:
                es_document = AudioPercolator
            case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
                es_document = RECAPPercolator
            case SEARCH_TYPES.OPINION:
                es_document = OpinionPercolator
            case _:
                logger.info(
                    f"'{alert_type}' Alert type indexing is not supported yet."
                )
                return

        indexing_counter = 0
        # Indexing the Alert objects
        for alert in queryset.iterator():
            logger.info(f"Indexing Alert with ID: {alert.pk}")
            es_save_alert_document.delay(
                alert.pk, es_document.__name__, index_name
            )
            indexing_counter += 1

        self.stdout.write(
            f"Successfully indexed {indexing_counter} alerts of type "
            f"{alert_type} from pk {pk_offset}."
        )
