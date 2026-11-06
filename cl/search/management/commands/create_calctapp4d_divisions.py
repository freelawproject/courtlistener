from typing import Any, NamedTuple

from django.core.management.base import CommandError, CommandParser
from django.db import models, transaction

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Court, Courthouse

PARENT_COURT_ID = "calctapp4d"


class Division(NamedTuple):
    """A division of the California Court of Appeal, 4th District.

    :ivar court_id: The ID of the court to create. It matches courts-db.
    :ivar number: The division's number.
    :ivar position: The court's position, between calctapp4d (350.34) and
    calctapp5d (350.35).
    :ivar city: The city where the division sits.
    :ivar county: The county of that city.
    """

    court_id: str
    number: int
    position: float
    city: str
    county: str


# Seats per the California Style Manual (4th ed.), § 1:17[B].
# See: https://github.com/freelawproject/courtlistener/issues/8283
DIVISIONS = [
    Division("calctapp4d1", 1, 350.341, "San Diego", "San Diego"),
    Division("calctapp4d2", 2, 350.342, "Riverside", "Riverside"),
    Division("calctapp4d3", 3, 350.343, "Santa Ana", "Orange"),
]


def check_preconditions() -> Court:
    """Check that the command can run without conflicts.

    :return: The parent court of the divisions.
    :raises CommandError: If the parent court is missing, or a division's ID
    or position is already taken.
    """
    if not (parent_court := Court.objects.filter(pk=PARENT_COURT_ID).first()):
        raise CommandError(f"Court not found: {PARENT_COURT_ID}")
    if taken := sorted(
        Court.objects.filter(
            models.Q(pk__in=[d.court_id for d in DIVISIONS])
            | models.Q(position__in=[d.position for d in DIVISIONS])
        ).values_list("pk", flat=True)
    ):
        raise CommandError(
            f"Division IDs or positions are already taken by: {taken}"
        )
    return parent_court


def create_division(division: Division, parent_court: Court) -> Court:
    """Create a division's court and its courthouse.

    :param division: The division to create.
    :param parent_court: The 4th District court.
    :return: The new court.
    """
    court = Court.objects.create(
        id=division.court_id,
        parent_court=parent_court,
        in_use=False,
        has_opinion_scraper=False,
        has_oral_argument_scraper=False,
        position=division.position,
        citation_string=f"Cal. Ct. App. 4th, Div. {division.number}",
        short_name=(
            "California Court of Appeals, 4th District, "
            f"Division {division.number}"
        ),
        full_name=(
            "California Court of Appeal, 4th District, "
            f"Division {division.number}"
        ),
        url=parent_court.url,
        jurisdiction=Court.STATE_APPELLATE,
    )
    Courthouse.objects.create(
        court=court,
        court_seat=None,
        city=division.city,
        county=division.county,
        state="CA",
        country_code="US",
    )
    return court


def find_rows_referencing_divisions() -> list[str]:
    """Find rows that would be lost or changed if the divisions are deleted.

    Courthouses are left out because the command created them, and history
    rows are left out because deletes don't touch them.

    :return: A description of each model with rows that reference a
    division, with the row count.
    """
    division_ids = [d.court_id for d in DIVISIONS]
    found = []
    for relation in Court._meta.related_objects:
        if (
            relation.related_model is Courthouse
            or relation.on_delete is models.DO_NOTHING
        ):
            continue
        model = relation.related_model
        lookup = {f"{relation.field.name}__in": division_ids}
        if count := model._default_manager.filter(**lookup).count():
            found.append(f"{model._meta.label}.{relation.field.name}: {count}")
    return found


def rollback(dry_run: bool) -> None:
    """Delete the division courts and their courthouses.

    :param dry_run: Whether to only log what would change.
    :raises CommandError: If other rows reference a division, because
    deleting it would delete or change them.
    """
    if found := find_rows_referencing_divisions():
        raise CommandError(
            f"Rows reference the divisions, so they can't be deleted: {found}"
        )

    with transaction.atomic():
        for court in Court.objects.filter(
            pk__in=[d.court_id for d in DIVISIONS]
        ):
            if dry_run:
                logger.info("Would delete %s and its courthouses", court.pk)
                continue
            court.delete()
            logger.info("Deleted %s and its courthouses", court.pk)


class Command(VerboseCommand):
    """Create the courts for the divisions of the California Court of Appeal,
    4th District."""

    help = (
        "Create the courts and courthouses for the 3 divisions of the "
        "California Court of Appeal, 4th District. It runs once: it stops "
        "without changes if a division already exists. To undo a run, use "
        "--rollback."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the command's arguments.

        :param parser: The command's argument parser.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Log what would change without changing anything.",
        )
        parser.add_argument(
            "--rollback",
            action="store_true",
            default=False,
            help="Undo a previous run: delete the division courts and their "
            "courthouses. Stops if other rows, such as dockets, reference a "
            "division.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Create the division courts, or undo a previous run."""
        super().handle(*args, **options)
        dry_run = options["dry_run"]
        if options["rollback"]:
            rollback(dry_run)
            return
        parent_court = check_preconditions()

        if dry_run:
            for division in DIVISIONS:
                logger.info(
                    "Would create %s at %s", division.court_id, division.city
                )
            return

        # One transaction, so a failure leaves no partial rows behind
        with transaction.atomic():
            for division in DIVISIONS:
                court = create_division(division, parent_court)
                logger.info("Created %s at %s", court.pk, division.city)
