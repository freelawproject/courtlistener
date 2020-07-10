from django.conf import settings
from django.core.mail import send_mail
from django.template import loader

from cl.api.utils import get_replication_statuses
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = (
        "Check that replication lag doesn't grow too high and send an "
        "alert if there's a problem."
    )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        bad_slots = []
        statuses = get_replication_statuses()
        for server_name, rows in statuses.items():
            for row in rows:
                if row["lsn_distance"] > settings.MAX_REPLICATION_LAG:
                    bad_slots.append(
                        "Slot '%s' on '%s' is lagging by %s bytes."
                        % (row["slot_name"], server_name, row["lsn_distance"])
                    )

        if bad_slots:
            subject = "Replication is lagging on %s slots" % len(bad_slots)
            template = loader.get_template("emails/replication_lag_email.txt")
            send_mail(
                subject=subject,
                message=template.render({"bad_slots": bad_slots}),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin[1] for admin in settings.ADMINS],
            )
