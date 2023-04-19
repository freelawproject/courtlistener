import random
from datetime import date
from typing import Any, Dict, Tuple, Union

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.encoding import force_bytes
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.alerts.models import RealTimeQueue
from cl.audio.models import Audio
from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.lib.import_lib import get_scotus_judges
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import lookup_judges_by_messy_str
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.management.commands import cl_scrape_opinions
from cl.scrapers.models import ErrorLog
from cl.scrapers.tasks import process_audio_file
from cl.scrapers.utils import (
    get_binary_content,
    get_extension,
    update_or_create_docket,
)
from cl.search.models import SEARCH_TYPES, SOURCES, Court, Docket

cnt = CaseNameTweaker()


@transaction.atomic
def save_everything(
    items: Dict[str, Union[Docket, Audio]],
    index: bool = False,
    backscrape: bool = False,
) -> None:
    docket, af = items["docket"], items["audio_file"]
    docket.save()
    af.docket = docket
    af.save(index=index)
    candidate_judges = []
    if af.docket.court_id != "scotus":
        if af.judges:
            candidate_judges = lookup_judges_by_messy_str(
                af.judges, docket.court.pk, af.docket.date_argued
            )
    else:
        candidate_judges = get_scotus_judges(af.docket.date_argued)

    for candidate in candidate_judges:
        af.panel.add(candidate)
    if not backscrape:
        RealTimeQueue.objects.create(
            item_type=SEARCH_TYPES.ORAL_ARGUMENT, item_pk=af.pk
        )


@transaction.atomic
def make_objects(
    item: Dict[str, Any],
    court: Court,
    sha1_hash: str,
    content: bytes,
) -> Tuple[Docket, Audio]:
    blocked = item["blocked_statuses"]
    if blocked:
        date_blocked = date.today()
    else:
        date_blocked = None

    case_name_short = item.get("case_name_shorts") or cnt.make_case_name_short(
        item["case_names"]
    )

    docket = update_or_create_docket(
        item["case_names"],
        case_name_short,
        court.pk,
        item.get("docket_numbers", ""),
        item.get("source") or Docket.SCRAPER,
        blocked=blocked,
        date_blocked=date_blocked,
        date_argued=item["case_dates"],
    )

    audio_file = Audio(
        judges=item.get("judges", ""),
        source=item.get("cluster_source") or SOURCES.COURT_WEBSITE,
        case_name=item["case_names"],
        case_name_short=case_name_short,
        sha1=sha1_hash,
        download_url=item["download_urls"],
        blocked=blocked,
        date_blocked=date_blocked,
    )

    cf = ContentFile(content)
    extension = get_extension(content)
    if extension not in [".mp3", ".wma"]:
        extension = f".{item['download_urls'].lower().rsplit('.', 1)[1]}"
    file_name = trunc(item["case_names"].lower(), 75) + extension
    audio_file.file_with_date = docket.date_argued
    audio_file.local_path_original_file.save(file_name, cf, save=False)

    return docket, audio_file


class Command(cl_scrape_opinions.Command):
    def scrape_court(
        self,
        site,
        full_crawl: bool = False,
        backscrape: bool = False,
    ) -> None:
        # Get the court object early for logging
        # opinions.united_states.federal.ca9_u --> ca9
        court_str = site.court_id.split(".")[-1].split("_")[0]
        court = Court.objects.get(pk=court_str)

        dup_checker = DupChecker(court, full_crawl=full_crawl)
        abort = dup_checker.abort_by_url_hash(site.url, site.hash)
        if abort:
            return

        if site.cookies:
            logger.info(f"Using cookies: {site.cookies}")
        for i, item in enumerate(site):
            msg, r = get_binary_content(
                item["download_urls"],
                site.cookies,
                method=site.method,
            )
            if msg:
                logger.warning(msg)
                ErrorLog(log_level="WARNING", court=court, message=msg).save()
                continue

            content = site.cleanup_content(r.content)

            current_date = item["case_dates"]
            try:
                next_date = site[i + 1]["case_dates"]
            except IndexError:
                next_date = None

            # request.content is sometimes a str, sometimes unicode, so
            # force it all to be bytes, pleasing hashlib.
            sha1_hash = sha1(force_bytes(content))
            onwards = dup_checker.press_on(
                Audio,
                current_date,
                next_date,
                lookup_value=sha1_hash,
                lookup_by="sha1",
            )
            if dup_checker.emulate_break:
                break

            if onwards:
                # Not a duplicate, carry on
                logger.info(
                    f"Adding new document found at: {item['download_urls'].encode()}"
                )
                dup_checker.reset()

                docket, audio_file = make_objects(
                    item, court, sha1_hash, content
                )

                save_everything(
                    items={"docket": docket, "audio_file": audio_file},
                    index=False,
                    backscrape=backscrape,
                )
                process_audio_file.apply_async(
                    (audio_file.pk,), countdown=random.randint(0, 3600)
                )

                logger.info(
                    "Successfully added audio file {pk}: {name}".format(
                        pk=audio_file.pk,
                        name=item["case_names"].encode(),
                    )
                )

        # Update the hash if everything finishes properly.
        logger.info(f"{site.court_id}: Successfully crawled oral arguments.")
        if not full_crawl:
            # Only update the hash if no errors occurred.
            dup_checker.update_site_hash(site.hash)
