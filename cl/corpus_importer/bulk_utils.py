from celery import chain

from cl.corpus_importer.tasks import get_pacer_doc_by_rd
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.lib.pacer_session import ProxyPacerSession, SessionData
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument


def make_bankr_docket_number(docket_number: str, office_code: str) -> str:
    """Combine the office number and core docket number to make a nice one

    E.g., docket number of 1421168 + office number of 2 becomes '2:14-bk-21168'

    :param docket_number: The docket number from the FJC IDB, as a string of
    numbers.
    :param office_code: The office code
    """
    return f"{office_code}:{docket_number[:2]}-bk-{docket_number[-5:]}"


def get_petitions(
    options,
    pacer_username: str,
    pacer_password: str,
    tag: str,
    tag_petitions: str,
) -> None:
    """Get dockets by tag, find item 1, download and tag it."""
    rds = (
        RECAPDocument.objects.filter(
            tags__name=tag,
            document_number="1",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=False,
        )
        .exclude(pacer_doc_id="")
        .order_by("pk")
        .values_list("pk", flat=True)
        .iterator()
    )
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = ProxyPacerSession(
        username=pacer_username, password=pacer_password
    )
    session.login()
    for i, rd_pk in enumerate(rds):
        if i < options["offset"]:
            i += 1
            continue
        if i >= options["limit"] > 0:
            break

        if i % 1000 == 0:
            session = ProxyPacerSession(
                username=pacer_username, password=pacer_password
            )
            session.login()
            logger.info(f"Sent {i} tasks to celery so far.")
        logger.info("Doing row %s", i)
        throttle.maybe_wait()
        chain(
            get_pacer_doc_by_rd.s(
                rd_pk,
                SessionData(session.cookies, session.proxy_address),
                tag=tag_petitions,
            ).set(queue=q),
            extract_recap_pdf.si(rd_pk).set(queue=q),
        ).apply_async()
