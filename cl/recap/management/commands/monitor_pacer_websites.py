# coding=utf-8
from __future__ import print_function

import requests
from django.conf import settings
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


def check_if_global_outage(session, url):
    """Use our lambda proxy to see if it's actually down for me or if it's
    down for everybody

    :param session: A requests.Session object
    :param url: A URL to check
    :return True if unavailable to our proxy, else False.
    """
    api_url = settings.AWS_LAMBDA_PROXY_URL
    response = session.get(api_url, params={"url": url}, timeout=20)
    if response.status_code != HTTP_200_OK:
        # Something went wrong with our request
        print(response.json())
        raise requests.RequestException("Didn't use proxy API correctly.")

    return response


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
            # Didn't get it from our server, but what about from the cloud
            logger.info(
                "After %s seconds, didn't get URL '%s' from our server, "
                "trying globally...",
                (now() - t1).seconds,
                url,
            )
            try:
                proxy_response = check_if_global_outage(session, url)
            except requests.RequestException as e:
                logger.error("Problem hitting proxy: %s", e)
                continue
            else:
                j = proxy_response.json()
                if j["status_code"] is not None:
                    # Something went wrong locally but not globally. We need
                    # do do something about this.
                    logger.error(
                        "After %s seconds, failed to access %s's PACER "
                        "website from our server, but got it via our proxy "
                        "with status code: %s.",
                        (now() - t1).seconds,
                        court.pk,
                        j["status_code"],
                    )
                else:
                    logger.info(
                        "After %s seconds, %s's PACER website is down for us "
                        "and our proxy. OK.",
                        (now() - t1).seconds,
                        court.pk,
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
