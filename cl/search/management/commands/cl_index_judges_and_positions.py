from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import Person
from cl.search.documents import PersonDocument, PositionDocument
from cl.search.tasks import index_parent_and_child_docs


class Command(VerboseCommand):
    help = "Index existing Judge and Positions docs into Elasticsearch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The Person pk to start indexing from.",
        )
        parser.add_argument(
            "--queue",
            type=str,
            default="celery",
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        pk_offset = options["pk_offset"]
        queue = options["queue"]

        # Filter Person objects by pk_offset and query alert type to index.
        queryset = Person.objects.filter(pk__gte=pk_offset).order_by("pk")
        indexing_counter = 0
        # Indexing judges
        throttle = CeleryThrottle(queue_name=queue)
        for person in queryset.iterator():
            if not person.is_judge:
                continue
            logger.info(f"Indexing Person with ID: {person.pk}")
            throttle.maybe_wait()
            index_parent_and_child_docs.si(
                person.pk, PersonDocument, PositionDocument
            ).set(queue=queue).apply_async()
            indexing_counter += 1

        self.stdout.write(
            f"Successfully indexed {indexing_counter} Judges from pk {pk_offset}."
        )
