import ast
import sys
from typing import Iterable

from django.apps import apps
from django.conf import settings
from requests import Session

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.timer import print_timing
from cl.people_db.models import Person
from cl.search.models import Docket
from cl.search.tasks import add_items_to_solr, delete_items

VALID_OBJ_TYPES = (
    "audio.Audio",
    "people_db.Person",
    "search.Opinion",
    "search.RECAPDocument",
    "search.Docket",
)


def proceed_with_deletion(out, count, noinput):
    """
    Checks whether we want to proceed to delete (lots of) items
    """
    if noinput:
        return True

    proceed = True
    out.write("\n")
    yes_or_no = input(
        f"WARNING: Are you **sure** you want to delete all {count} items? [y/N] "
    )
    out.write("\n")
    if not yes_or_no.lower().startswith("y"):
        out.write("No action taken.\n")
        proceed = False

    if count > 10000 and proceed is True:
        # Double check...something might be off.
        yes_or_no = input(
            "Are you sure? There are an awful lot of items here? [y/N] "
        )
        if not yes_or_no.lower().startswith("y"):
            out.write("No action taken.\n")
            proceed = False

    return proceed


class Command(VerboseCommand):
    help = (
        "Adds, updates, deletes items in an index, committing changes and "
        "optimizing it, if requested."
    )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.solr_url = None
        self.si = None
        self.verbosity = None
        self.options = []
        self.type = None
        self.noinput = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=VALID_OBJ_TYPES,
            help="Because the Solr indexes are loosely bound to the database, "
            "commands require that the correct model is provided in this "
            "argument. Current choices are %s" % ", ".join(VALID_OBJ_TYPES),
        )
        parser.add_argument(
            "--solr-url",
            type=str,
            help="When swapping cores, it can be valuable to use a temporary "
            "Solr URL, overriding the default value that's in the "
            "settings, e.g., http://127.0.0.1:8983/solr/swap_core",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Do NOT prompt the user for input of any kind. Useful in "
            "tests, but can disable important warnings.",
        )
        parser.add_argument(
            "--queue",
            type=str,
            default="celery",
            help="The celery queue where the tasks should be processed.",
        )

        actions_group = parser.add_mutually_exclusive_group()
        actions_group.add_argument(
            "--update",
            action="store_true",
            default=False,
            help="Run the command in update mode. Use this to add or update "
            "items.",
        )
        actions_group.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Run the command in delete mode. Use this to remove  items "
            "from the index. Note that this will not delete items from "
            "the index that do not continue to exist in the database.",
        )

        parser.add_argument(
            "--optimize",
            action="store_true",
            default=False,
            help="Run the optimize command against the current index after "
            "any updates or deletions are completed.",
        )
        parser.add_argument(
            "--optimize-everything",
            action="store_true",
            default=False,
            help="Optimize all indexes that are registered with Solr.",
        )
        parser.add_argument(
            "--do-commit",
            action="store_true",
            default=False,
            help="Performs a simple commit and nothing more.",
        )

        act_upon_group = parser.add_mutually_exclusive_group()
        act_upon_group.add_argument(
            "--everything",
            action="store_true",
            default=False,
            help="Take action on everything in the database",
        )
        act_upon_group.add_argument(
            "--query",
            type=str,
            help="Take action on items fulfilling a query. Queries should be "
            "formatted as Python dicts such as: \"{'court_id':'haw'}\"",
        )
        act_upon_group.add_argument(
            "--items",
            type=int,
            nargs="*",
            help="Take action on a list of items using a single "
            "Celery task",
        )
        act_upon_group.add_argument(
            "--datetime",
            type=valid_date_time,
            help="Take action on items newer than a date (YYYY-MM-DD) or a "
            "date and time (YYYY-MM-DD HH:MM:SS)",
        )

        parser.add_argument(
            "--start-at",
            type=int,
            default=0,
            help="For use with the --everything flag, skip this many items "
            "before starting the processing.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.verbosity = int(options.get("verbosity", 1))
        self.options = options
        self.noinput = options["noinput"]
        if not self.options["optimize_everything"]:
            self.solr_url = options["solr_url"]
            self.si = ExtraSolrInterface(self.solr_url, mode="rw")
            self.type = options["type"]

        if options["update"]:
            if self.verbosity >= 1:
                self.stdout.write("Running in update mode...\n")
            if options.get("everything"):
                self.add_or_update_all()
            elif options.get("datetime"):
                self.add_or_update_by_datetime(options["datetime"])
            elif options.get("query"):
                self.stderr.write("Updating by query not implemented.")
                sys.exit(1)
            elif options.get("items"):
                self.add_or_update(*options["items"])

        elif options.get("delete"):
            if self.verbosity >= 1:
                self.stdout.write("Running in deletion mode...\n")
            if options.get("everything"):
                self.delete_all()
            elif options.get("datetime"):
                self.delete_by_datetime(options["datetime"])
            elif options.get("query"):
                self.delete_by_query(options["query"])
            elif options.get("items"):
                self.delete(*options["items"])

        if options.get("do_commit"):
            self.si.commit()

        if options.get("optimize"):
            self.optimize()

        if options.get("optimize_everything"):
            self.optimize_everything()

        self.si.conn.http_connection.close()
        if not any(
            [
                options["update"],
                options.get("delete"),
                options.get("do_commit"),
                options.get("optimize"),
                options.get("optimize_everything"),
            ]
        ):
            self.stderr.write(
                "Error: You must specify whether you wish to "
                "update, delete, commit, or optimize your "
                "index.\n"
            )
            sys.exit(1)

    def process_queryset(self, iterable: Iterable, count: int) -> None:
        """Chunks the queryset passed in, and dispatches it to Celery for
        adding to the index.

        :param iterable: An iterable of items to add to Solr.
        :param count: The number of items that will be processed.
        """
        # The count to send in a single Celery task
        chunk_size = 100

        queue = self.options["queue"]
        start_at = self.options["start_at"]
        # Set low throttle. Higher values risk crashing Redis.
        throttle = CeleryThrottle(queue_name=queue)
        processed_count = 0
        chunk = []
        for item in iterable:
            processed_count += 1
            if processed_count < start_at:
                continue
            last_item = count == processed_count
            chunk.append(item)
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()
                add_items_to_solr.apply_async(
                    args=(chunk, self.type), queue=queue
                )
                chunk = []
                sys.stdout.write(
                    "\rProcessed {}/{} ({:.0%})".format(
                        processed_count, count, processed_count * 1.0 / count
                    )
                )
                self.stdout.flush()
        self.stdout.write("\n")

    @print_timing
    def delete(self, items):
        """
        Given a list of items, delete them.
        """
        self.stdout.write(f"Deleting items(s): {items}\n")
        delete_items.delay(items, self.type)

    def delete_all(self):
        """
        Deletes all items from the index.
        """
        count = self.si.query("*").add_extra(caller="cl_update_index").count()

        if proceed_with_deletion(self.stdout, count, self.noinput):
            self.stdout.write(
                "Removing all items from your index because you said so.\n"
            )
            self.stdout.write("  Marking all items as deleted...\n")
            self.si.delete_all()
            self.stdout.write("  Committing the deletion...\n")
            self.si.commit()
            self.stdout.write(
                f"\nDone. The index located at: {self.solr_url}\nis now empty.\n"
            )

    @print_timing
    def delete_by_datetime(self, dt):
        """
        Given a datetime, deletes all items in the index newer than that time.

        Relies on the items still being in the database.
        """
        model = apps.get_model(self.type)
        qs = (
            model.objects.filter(date_created__gt=dt)
            .order_by()
            .values_list("pk", flat=True)
        )
        count = qs.count()
        if proceed_with_deletion(self.stdout, count, self.noinput):
            self.stdout.write(f"Deleting all item(s) newer than {dt}\n")
            self.si.delete(list(qs))
            self.si.commit()

    @print_timing
    def delete_by_query(self, query):
        """
        Given a query, deletes all the items that match that query.
        """
        query_dict = ast.literal_eval(query)
        count = self.si.query(self.si.Q(**query_dict)).count()
        if proceed_with_deletion(self.stdout, count, self.noinput):
            self.stdout.write(
                f"Deleting all item(s) that match the query: {query}\n"
            )
            self.si.delete(queries=self.si.Q(**query_dict))
            self.si.commit()

    @print_timing
    def add_or_update(self, *items):
        """
        Given an item, adds it to the index, or updates it if it's already
        in the index.
        """
        self.stdout.write(f"Adding or updating item(s): {list(items)}\n")
        add_items_to_solr(items, self.type)

    @print_timing
    def add_or_update_by_datetime(self, dt):
        """
        Given a datetime, adds or updates all items newer than that time.
        """
        self.stdout.write(f"Adding or updating items(s) newer than {dt}\n")
        model = apps.get_model(self.type)
        qs = (
            model.objects.filter(date_created__gte=dt)
            .order_by()
            .values_list("pk", flat=True)
        )
        count = qs.count()
        qs = qs.iterator()
        self.process_queryset(qs, count)

    @print_timing
    def add_or_update_all(self):
        """
        Iterates over the entire corpus, adding it to the index. Can be run on
        an empty index or an existing one.

        If run on an existing index, existing items will be updated, but no
        items will be deleted.
        """
        self.stdout.write("Adding or updating all items...\n")
        model = apps.get_model(self.type)
        if model == Person:
            q = model.objects.filter(is_alias_of=None).prefetch_related(
                "positions"
            )
            # Filter out non-judges -- they don't get searched.
            q = [item.pk for item in q if item.is_judge]
            count = len(q)
        elif model == Docket:
            q = Docket.objects.filter(
                source__in=Docket.RECAP_SOURCES
            ).values_list("pk", flat=True)
            count = q.count()
            q = q.iterator()
        else:
            q = model.objects.values_list("pk", flat=True)
            count = q.count()
            q = q.iterator()
        self.process_queryset(q, count)

    @print_timing
    def optimize(self):
        """Runs the Solr optimize command."""
        self.stdout.write("Optimizing the index...")
        self.si.optimize()
        self.stdout.write("done.\n")

    @print_timing
    def optimize_everything(self):
        """Run the optimize command on all indexes."""
        urls = set(settings.SOLR_URLS.values())
        self.stdout.write(f"Found {len(urls)} indexes. Optimizing...\n")
        with Session() as session:
            for url in urls:
                self.stdout.write(f" - {url}\n")
                try:
                    si = ExtraSolrInterface(url, http_connection=session)
                except EnvironmentError:
                    self.stderr.write("   Couldn't load schema!")
                    continue
                si.optimize()
        self.stdout.write("Done.\n")
