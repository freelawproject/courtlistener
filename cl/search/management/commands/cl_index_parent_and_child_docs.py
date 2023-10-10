from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import Person
from cl.search.documents import (
    DocketDocument,
    ESRECAPDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import index_parent_and_child_docs


class Command(VerboseCommand):
    help = "Index existing Parent and Children docs into Elasticsearch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--search-type",
            type=str,
            required=True,
            choices=[SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP],
            help=f"The search type models to index: ({', '.join([SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP])})",
        )

        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The parent document pk to start indexing from.",
        )
        parser.add_argument(
            "--queue",
            type=str,
            required=True,
            default="celery",
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        pk_offset = options["pk_offset"]
        queue = options["queue"]
        search_type = options["search_type"]

        throttle = CeleryThrottle(queue_name=queue)
        indexing_counter = 0
        match search_type:
            case SEARCH_TYPES.PEOPLE:
                # Get Person objects by pk_offset.
                queryset = Person.objects.filter(pk__gte=pk_offset).order_by(
                    "pk"
                )
                # Indexing judges and positions.
                for person in queryset.iterator():
                    if not person.is_judge:
                        continue
                    logger.info(f"Indexing Person with ID: {person.pk}")
                    throttle.maybe_wait()
                    index_parent_and_child_docs.si(
                        person.pk, SEARCH_TYPES.PEOPLE
                    ).set(queue=queue).apply_async()
                    indexing_counter += 1
                self.stdout.write(
                    f"Successfully indexed {indexing_counter} Judges from pk {pk_offset}."
                )
            case SEARCH_TYPES.RECAP:
                # Get Docket objects by pk_offset.
                queryset = Docket.objects.all().order_by("pk")

                # Indexing Dockets and RECAPDocuments.
                for docket in queryset.iterator():
                    logger.info(f"Indexing Docket with ID: {docket.pk}")
                    throttle.maybe_wait()
                    index_parent_and_child_docs.si(
                        docket.pk, SEARCH_TYPES.RECAP
                    ).set(queue=queue).apply_async()
                    indexing_counter += 1

                self.stdout.write(
                    f"Successfully indexed {indexing_counter} Dockets from pk {pk_offset}."
                )
