import time

import pgtrigger
from django.db import IntegrityError, transaction
from django.db.models import F

from cl.lib.command_utils import CommandError, VerboseCommand, logger
from cl.search.models import Docket
from cl.settings import TESTING


class Command(VerboseCommand):
    help = "Populate `Docket.docket_number_raw` using `docket_number`"

    def add_arguments(self, parser):
        parser.add_argument(
            "start-id", help="Value of Docket.id to start from", type=int
        )
        parser.add_argument(
            "end-id", help="Last value of Docket.id to update", type=int
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        start_id = options["start_id"]
        end_id = options["end_id"]
        if end_id <= start_id:
            raise ValueError("`end-id` should be bigger thant `start-id`")

        max_ids_per_command_call = 10_000_000
        if end_id - start_id > max_ids_per_command_call:
            logger.warning(
                """Setting `end_id` to %s from input value %s.
                You should VACUUM the table to prevent using too much space from the updated tuples.
                We support 10M ids per command call
                """,
                start_id + max_ids_per_command_call,
                end_id,
            )
            end_id = start_id + max_ids_per_command_call

        batch_size = 100_000
        for batch_start in range(start_id, end_id, batch_size):
            batch_end = batch_start + batch_size
            # a sanity check to prevent usage of this command in the future,
            # once all docket_number_raw logic is in place
            qs = Docket.objects.filter(id__gte=batch_start, id__lt=batch_end)
            sample_docket = qs.first()
            if sample_docket is None:
                logger.info(
                    "Docket.id range is empty %s %s", batch_start, batch_end
                )
                break

            if sample_docket.docket_number_raw != "":
                raise CommandError(
                    "Docket.docket_number_raw %s already exists. This command assumes it to be empty",
                    sample_docket.id,
                )

            logger.info(
                "Populating `docket_number_raw` for Docket.id %s to %s",
                batch_start,
                batch_end,
            )

            with pgtrigger.ignore("search.Docket:update_update"):
                with transaction.atomic():
                    try:
                        qs.update(docket_number_raw=F("docket_number"))
                    except IntegrityError:
                        logger.error(
                            "Docket.docket_number_raw population failed",
                            exc_info=True,
                        )

            # prevent affecting all tests with this sleep
            if not TESTING:
                logger.info("Finished batch update. Sleeping for 5 seconds")
                time.sleep(5)
