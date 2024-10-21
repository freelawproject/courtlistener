import time

from cl.alerts.management.commands.cl_send_scheduled_alerts import (
    query_and_send_alerts_by_rate,
)
from cl.alerts.models import Alert
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = """Send real-time alerts scheduled by the Percolator every 5 minutes.
     This process is performed to accumulate alerts that can be grouped into a
     single email if they belong to the same user. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            help="Use this flag for testing purposes.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        testing_mode = options.get("testing_mode", False)
        while True:
            query_and_send_alerts_by_rate(Alert.REAL_TIME)
            if testing_mode:
                # Perform only 1 iteration for testing purposes.
                break

            # Wait for 5 minutes.
            time.sleep(300)
