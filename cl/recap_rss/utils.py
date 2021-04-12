from typing import Dict

from django.conf import settings

from cl.lib.types import EmailType

emails: Dict[str, EmailType] = {
    "changed_rss_feed": {
        "subject": "PACER RSS feed changed for: %s",
        "body": "Dear admin:\n\n%s's RSS feed has changed:\n\n"
        " - %s\n"
        " + %s\n\n"
        "You should probably tell the court this is unacceptable.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
    "stale_feed": {
        "subject": "PACER feed gone stale at: %s",
        "body": "Dear admin:\n\n"
        "%s's RSS feed has not had updates for %s minutes. You can see their "
        "feed here:\n\n"
        "  %s\n\n"
        "You should probably tell the court this is an issue. Maybe their "
        "CM/ECF administrator, IT staff, or director of operations?",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
}
