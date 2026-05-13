import requests
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.urls import reverse

from cl.lib.command_utils import VerboseCommand
from cl.stats.utils import get_replication_statuses


class Command(VerboseCommand):
    help = (
        "Check that replication lag doesn't grow too high and post an "
        "alert to Slack if there's a problem."
    )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        bad_slots = []
        statuses = get_replication_statuses()
        for server_name, rows in statuses.items():
            for row in rows:
                if row["lsn_distance"] is None:
                    continue
                if row["lsn_distance"] > settings.MAX_REPLICATION_LAG:
                    bad_slots.append(
                        f"Slot `{row['slot_name']}` on `{server_name}` "
                        f"is lagging by {intcomma(row['lsn_distance'])} bytes."
                    )

        if not bad_slots:
            return

        if not settings.SLACK_REPLICATION_WEBHOOK_URL:
            self.stderr.write(
                "SLACK_REPLICATION_WEBHOOK_URL not set; cannot alert."
            )
            return

        status_url = (
            f"https://www.courtlistener.com{reverse('replication_status')}"
        )
        text = (
            f":rotating_light: *Replication lag exceeded threshold "
            f"on {len(bad_slots)} slot(s):*\n"
            + "\n".join(f"• {s}" for s in bad_slots)
            + f"\n<{status_url}|View live status>"
        )

        response = requests.post(
            settings.SLACK_REPLICATION_WEBHOOK_URL,
            json={"text": text},
            timeout=10,
        )
        response.raise_for_status()