from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.mail import send_mail
from django.template import loader

from cl.lib.command_utils import VerboseCommand
from cl.stats.utils import get_replication_statuses


class Command(VerboseCommand):
    help = (
        "Check that replication lag doesn't grow too high and send an "
        "alert if there's a problem."
    )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        bad_slots = []
        statuses = get_replication_statuses()
        for server_name, rows in statuses.items():
            for row in rows:
                if row["lsn_distance"] > settings.MAX_REPLICATION_LAG:
                    bad_slots.append(
                        f"Slot '{row['slot_name']}' on '{server_name}' is "
                        f"lagging by {intcomma(row['lsn_distance'])} bytes."
                    )

        if bad_slots:
            subject = f"Replication is lagging on {len(bad_slots)} slots"
            template = loader.get_template("emails/replication_lag_email.txt")
            send_mail(
                subject=subject,
                message=template.render({"bad_slots": bad_slots}),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin[1] for admin in settings.MANAGERS],
            )
