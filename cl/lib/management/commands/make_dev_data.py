from django.core.management.base import CommandParser

from cl.alerts.factories import AlertFactory, DocketAlertWithParentsFactory
from cl.api.factories import WebhookEventWithParentsFactory
from cl.audio.factories import AudioWithParentsFactory
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.factories import PersonFactory, PersonWithChildrenFactory
from cl.recap.factories import FjcIntegratedDatabaseFactory
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketEntryForDocketFactory,
    DocketEntryReuseParentsFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    DocketWithChildrenFactory,
    OpinionClusterWithParentsFactory,
    OpinionWithParentsFactory,
    ParentheticalWithParentsFactory,
)
from cl.users.factories import UserFactory

FACTORIES = {
    # Search app
    100: CourtFactory,
    101: DocketFactory,
    102: OpinionClusterWithParentsFactory,
    103: OpinionWithParentsFactory,
    104: DocketEntryWithParentsFactory,
    105: ParentheticalWithParentsFactory,
    106: FjcIntegratedDatabaseFactory,
    107: DocketEntryForDocketFactory,
    108: DocketEntryReuseParentsFactory,
    # People DB app
    200: PersonFactory,
    201: PersonWithChildrenFactory,
    # Users
    300: UserFactory,
    # Citations
    400: CitationWithParentsFactory,
    # Alerts
    500: DocketAlertWithParentsFactory,
    501: AlertFactory,
    # Audio
    600: AudioWithParentsFactory,
    # API
    700: WebhookEventWithParentsFactory,
}
factories_str = "\n".join([f"{k}: {v}" for k, v in FACTORIES.items()])


class Command(VerboseCommand):
    help = "Create dummy data in your system for development purposes"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help=f"How many items to create",
        )
        parser.add_argument(
            "--make-objects",
            type=int,
            nargs="+",
            required=False,
            help=f"Which type of objects do you want. Select by number from "
            f"(multiple numbers allowed, separated by spaces): "
            f"\n{factories_str}",
        )
        parser.add_argument(
            "--list-objects",
            action="store_true",
            required=False,
            help="Print the list of possible objects",
        )
        parser.add_argument(
            "--parent-id",
            type=int,
            required=False,
            help=f"The parent of the object(s) being made",
        )

    def handle(self, *args, **options) -> None:
        super(Command, self).handle(*args, **options)

        if options["list_objects"]:
            for number, obj in FACTORIES.items():
                print(f"{number}:\t{obj}")
            exit(0)

        count = options["count"]
        logger.info(
            f"Creating dummy data. Making at least {count} "
            f"objects of each type."
        )
        parent_id = options["parent_id"] if options["parent_id"] else None

        if options["make_objects"] is None:
            # Just make a bit of everything. Start with a docket and build all
            # the children below it.
            for note, Factory in (
                (
                    "dockets and all their dependent objects",
                    DocketWithChildrenFactory,
                ),
                ("judges and all their positions", PersonWithChildrenFactory),
                ("users and super users", UserFactory),
                (
                    "citations and their parent objects",
                    CitationWithParentsFactory,
                ),
                (
                    "docket alerts and their parent objects",
                    DocketAlertWithParentsFactory,
                ),
            ):
                logger.info(f"Making {count} {note}")
                Factory.create_batch(count)
        else:
            # The user requested something specific. Build that thing and all
            # the parents above it.
            for object_type in options["make_objects"]:
                Factory = FACTORIES[object_type]
                logger.info(
                    f"Making {count} items and their dependant parents using "
                    f"object type #{object_type}: {Factory}"
                )
                if parent_id:
                    Factory.create_batch(count, parent_id=parent_id)
                else:
                    Factory.create_batch(count)
