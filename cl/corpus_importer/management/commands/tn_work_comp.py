# !/usr/bin/python
# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes

from cl.lib.command_utils import VerboseCommand
from cl.lib.crypto import sha1
from cl.people_db.models import Person
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.search.models import Court, Opinion, Docket


def process_date(date_str):
    if "-" in date_str[:4]:
        return datetime.strptime(date_str[:10], "%m-%d-%Y").date()
    return datetime.strptime(date_str[:10], "%Y-%m-%d").date()


def make_judges(case):
    """Make judge or panel

    :param case: Processed case data.
    :type: dict
    :return: Judge name(s)
    :type: str
    """
    if case["court"] == "tennworkcompcl":
        return Person.objects.get(pk=case["lead_author_id"]).name_full

    if process_date(case["pub_date"]).year < 2020:
        # There have only been two variations of the board.
        return ", ".join(
            [
                "Marshall L. Davidson, III",
                "David F. Hensley",
                "Timothy W. Conner",
            ]
        )
    return ", ".join(
        ["David F. Hensley", "Timothy W. Conner", "Pele I. Godkin"]
    )


def make_case_dictionary(case):
    """Make case processing dictionary.

    The dictionary can be loaded into make_objects from cl_scrape_opininons
    :param case: A case loaded from a preprocessed json file.
    :type: dict
    :return: Processed data used to add new tenn workers comp case.
    :type: dict
    """

    return {
        "source": Docket.DEFAULT,
        "cluster_source": "D",
        "case_names": case["title"],
        "case_dates": process_date(case["pub_date"]),
        "precedential_statuses": "Published",
        "docket_numbers": case["docket"],
        "judges": make_judges(case),
        "author_id": case["lead_author_id"],
        "author": Person.objects.get(pk=case["lead_author_id"]),
        "date_filed_is_approximate": False,
        "blocked_statuses": False,
        "neutral_citations": " ".join(
            [str(cite) for cite in case["neutral_citation"]]
        ),
        "download_urls": case["pdf_url"],
    }


def import_tn(filepath):
    """Corpus importer for Tenn Workers Comp. Boards

    :param filepath: Path to cleaned json data used to import cases.
    :return: None
    """
    with open(filepath, "r") as f:
        cases = json.loads(f.read())

    for case in cases:
        if not case["success"]:
            logging.warn(
                "No PDF document available for this case %s", case["title"]
            )
            continue

        if len(Opinion.objects.filter(download_url=case["pdf_url"])) > 0:
            logging.warn("Case appears in system already %s", case["title"])
            continue

        item = make_case_dictionary(case)
        pdf_data = requests.get(case["pdf_url"]).content
        sha1_hash = sha1(force_bytes(pdf_data))

        if len(Opinion.objects.filter(sha1=sha1_hash)) > 0:
            logging.warn("PDF already in system, skip it")
            continue

        court = Court.objects.get(pk=case["court"])

        docket, opinion, cluster, citations, error = make_objects(
            item, court, sha1_hash, pdf_data,
        )
        opinion.author_str = case["judge"]

        if error:
            raise ValidationError("PDF failed to download.")

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            },
            index=False,
        )

        extract_doc_content.delay(
            opinion.pk, do_ocr=True, citation_jitter=True,
        )

        logging.warn("http://palin.local:8000%s" % cluster.get_absolute_url())

        logging.info(
            "Successfully added Tennessee object cluster: %s", cluster.id
        )


class Command(VerboseCommand):
    help = "Download and save Tennessee Workers Compensation data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath",
            default="cl/corpus_importer/tmp/tenn_data.json",
            help="The filepath of preprocessed tennessee workers comp data",
        )

    def handle(self, *args, **options):
        settings.DEBUG = False
        filepath = options["filepath"]
        import_tn(filepath)
