from http import HTTPStatus

import requests
from django.conf import settings
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.decorators import retry
from cl.lib.pacer import map_cl_to_pacer_id
from cl.search.models import Court


@retry(requests.RequestException, tries=2, backoff=1)
def check_and_log_url(session: requests.Session, url: str, timeout: int = 10):
    """Check if a URL is accessible by sending it a GET request

    :param session: A requests.Session object
    :param url: The URL to check
    :param timeout: How long to wait for the website to respond
    :return requests.Response object for the query, assuming it doesn't time
    out
    """
    return session.get(url, timeout=timeout, verify=False)


def check_if_global_outage(session, url, timeout=5):
    """Use our lambda proxy to see if it's actually down for me or if it's
    down for everybody

    :param session: A requests.Session object
    :param url: A URL to check
    :param timeout: The amount of time the *proxy* should wait (this function
    will wait a little longer)
    :return True if unavailable to our proxy, else False.
    """
    api_url = settings.AWS_LAMBDA_PROXY_URL
    response = session.get(
        api_url,
        params={"url": url, "timeout": timeout},
        # Make this timeout *after* the proxy would, so that we can get errors
        # from the proxy, not from here.
        timeout=timeout + 1,
    )
    if response.status_code != HTTPStatus.OK:
        # Something went wrong with our request
        print(response.json())
        raise requests.RequestException("Didn't use proxy API correctly.")

    return response


def make_simple_url(court) -> str:
    if court.pk == "cavc":
        return "https://efiling.uscourts.cavc.gov/"
    else:
        return f"https://ecf.{map_cl_to_pacer_id(court.pk)}.uscourts.gov/"


def down_for_only_me(session: requests.Session, url: str) -> bool:
    """Check if a URL is down just our server, or globally

    :return: True if the url is only down for me, or False if entirely up or
    entirely down.
    """
    try:
        check_and_log_url(session, url)
    except requests.RequestException:
        # Down from our server. Try from our proxy.
        try:
            proxy_response = check_if_global_outage(session, url)
        except requests.RequestException as e:
            logger.error("Problem hitting proxy: %s", e)
            raise e

        j = proxy_response.json()
        if j["status_code"] is not None:
            # Down from our server, but up from our proxy. Yikes!
            return True
        else:
            # Down from our server, and down from our proxy. OK.
            return False

    # Up from our server. OK.
    return False


def iterate_and_log_courts(courts):
    session = requests.Session()
    for court in courts:
        url = make_simple_url(court)
        logger.info("Checking url for %s: %s", court.pk, url)
        t1 = now()
        max_tries = 3
        try_number = 1
        while try_number <= max_tries:
            down_for_me = down_for_only_me(session, url)
            if not down_for_me:
                break
            try_number += 1
        else:
            # Tried `try_count` times, and it was always down just for me. Oof.
            # Use % instead of logging params to bypass Sentry issue grouping
            logger.error(
                "After %s seconds and %s tries, failed to access %s's PACER "
                "website from our server, but got it via our proxy each time."
                % ((now() - t1).seconds, try_number, court.pk)
            )


class Command(VerboseCommand):
    help = (
        "Monitor PACER websites and write errors to our logs. Because we "
        "use Sentry, errors in logs will surface as emails to admins."
    )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        courts = Court.federal_courts.all_pacer_courts()
        iterate_and_log_courts(courts)
