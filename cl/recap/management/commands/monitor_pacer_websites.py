# coding=utf-8
from __future__ import print_function

import requests
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.decorators import retry
from cl.lib.pacer import map_cl_to_pacer_id
from cl.search.models import Court


@retry(requests.RequestException)
def check_and_log_url(session, url, timeout=5):
    """Check if a URL is accessible by sending it a HEAD request

    :param session: A requests.Session object
    :param url: The URL to check
    :param timeout: How long to wait for the website to respond
    :return requests.Response object for the query, assuming it doesn't time
    out
    """
    return session.get(url, timeout=timeout, verify=False)


def make_simple_url(court):
    if court.pk == "cavc":
        return "https://efiling.uscourts.cavc.gov/"
    else:
        return "https://ecf.%s.uscourts.gov/" % map_cl_to_pacer_id(court.pk)


def iterate_and_log_courts(courts):
    session = requests.Session()
    for court in courts:
        url = make_simple_url(court)
        logger.info("Checking url for %s: %s", court.pk, url)
        t1 = now()
        try:
            response = check_and_log_url(session, url)
        except requests.RequestException as e:
            logger.error(
                "After %s seconds, failed to access URL %s with exception %s.",
                (now() - t1).seconds,
                url,
                e,
            )
        else:
            duration = (now() - t1).seconds
            if response.status_code == HTTP_200_OK:
                logger.info("Got 200 status code after %s seconds", duration)
            else:
                logger.error(
                    "Got status code of %s after %s seconds",
                    response.status,
                    duration,
                )


class Command(VerboseCommand):
    help = (
        "Monitor PACER websites and write errors to our logs. Because we "
        "use Sentry, errors in logs will surface as emails to admins."
    )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        courts = Court.federal_courts.all_pacer_courts()
        iterate_and_log_courts(courts)
