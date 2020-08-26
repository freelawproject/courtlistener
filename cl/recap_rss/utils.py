from django.conf import settings

emails = {
    "changed_rss_feed": {
        "subject": "PACER RSS feed changed for: %s",
        "body": "Dear admin:\n\n%s's RSS feed has changed:\n\n"
        " - %s\n"
        " + %s\n\n"
        "You should probably tell the court this is unacceptable.",
        "from": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
}
