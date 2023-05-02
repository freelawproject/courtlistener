import argparse
import json
import logging
import os
from glob import glob
from typing import IO, Union

from dateutil import parser
from django.utils.encoding import force_bytes

from cl.lib.command_utils import VerboseCommand
from cl.lib.crypto import sha1
from cl.people_db.models import Person
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.search.models import SOURCES, Court, Docket, Opinion


def make_item(case):
    """Make an import item for our save everything function

    :param case: Case data received from the court.
    :return: Case information.
    :type: dict
    """

    judges = case["judge"]
    first_name = judges.split(" ")[0].title()

    lead_author = Person.objects.get(
        positions__court_id=case["court"],
        is_alias_of=None,
        name_first=first_name,
    )

    # Four Panelists exist, one retired end of 2019 and the other joined.
    pub_date = parser.parse(case["pub_date"])
    if case["court"] == "tennworkcompapp":
        exclude = "Marshall" if pub_date.date().year == 2020 else "Pele"
        panelists_query = Person.objects.filter(
            positions__court_id=case["court"]
        ).exclude(name_first=exclude)
        panelists = ", ".join([x.name_full for x in panelists_query])
    else:
        panelists = case["judge"]

    return {
        "source": Docket.DIRECT_INPUT,
        "cluster_source": SOURCES.DIRECT_COURT_INPUT,
        "case_names": case["title"],
        "case_dates": pub_date,
        "precedential_statuses": "Published",
        "docket_numbers": case["docket"],
        "judges": panelists,
        "author_id": lead_author.id,
        "author": lead_author,
        "date_filed_is_approximate": False,
        "blocked_statuses": False,
        "citations": case["citation"],
        "download_urls": case["pdf_url"],
    }


def import_tn_corpus(
    log: bool,
    skip_until: Union[bool, str],
    file: IO,
    ocr_available: bool,
) -> None:
    """Import TN Corpus

    :param log: Should we view logging info
    :param skip_until: Label ID, if any, to process first, else False to
    indicate no skipping.
    :param file: Location of our overriding data json file
    :param ocr_available: Whether you can do OCR during the import
    :return: None
    """
    ready = False if skip_until else True

    if log:
        logging.getLogger().setLevel(logging.INFO)

    logging.info("Starting import")
    tn_corpus = sorted(json.load(file), key=lambda x: x["label"])
    if not ready:
        case = [x for x in tn_corpus if x["label"] == skip_until][0]
        logging.info(
            "Skipping until case %s labeled: %s", case["title"], case["label"]
        )
    courts = {
        "tennworkcompcl": Court.objects.get(pk="tennworkcompcl"),
        "tennworkcompapp": Court.objects.get(pk="tennworkcompapp"),
    }

    for case in tn_corpus:
        if case["label"] == skip_until:
            ready = True
        if not ready:
            continue
        logging.info(
            "Processing label:%s for case:%s", case["label"], case["title"]
        )
        pdf_path = glob(f"{os.path.dirname(file.name)}/{case['label']}/*.pdf")[
            0
        ]
        with open(pdf_path, "rb") as p:
            pdf_data = p.read()

        sha1_hash = sha1(force_bytes(pdf_data))
        ops = Opinion.objects.filter(sha1=sha1_hash)
        if len(ops) > 0:
            op = ops[0]
            logging.warning(
                "Document already in database. See: %s at %s"
                % (op.get_absolute_url(), op.cluster.case_name)
            )

        docket, opinion, cluster, citations = make_objects(
            make_item(case),
            courts[case["court"]],
            sha1_hash,
            pdf_data,
        )

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
            opinion.pk,
            ocr_available=ocr_available,
            citation_jitter=True,
        )
        logging.info(
            "Successfully added Tennessee object cluster: %s", cluster.id
        )


class Command(VerboseCommand):
    help = "Import TN data corpus received from TN Workers Comp boards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            type=argparse.FileType("r"),
            help="The filepath to our preprocessed data file.",
            required=True,
        )
        parser.add_argument(
            "--log",
            action="store_true",
            default=False,
            help="Choose to view info log lines.",
        )
        parser.add_argument(
            "--skip-until",
            help="Skip until to process",
            type=int,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        import_tn_corpus(
            options["log"],
            options["skip_until"],
            options["input_file"],
            ocr_available=True,
        )
