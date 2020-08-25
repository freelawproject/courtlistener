import itertools
import json
import logging
from glob import glob

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
from cl.search.models import Court, Docket, Opinion


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
    panelists = case["judge"]
    if case["court"] == "tennworkcompapp":
        exclude = (
            "Marshall"
            if parser.parse(case["pub_date"]).date().year == 2020
            else "Pele"
        )
        panelists_query = Person.objects.filter(
            positions__court_id=case["court"]
        ).exclude(name_first=exclude)
        panelists = ", ".join([x.name_full for x in panelists_query])

    return {
        "source": Docket.DIRECT_INPUT,
        "cluster_source": "D",
        "case_names": case["title"],
        "case_dates": parser.parse(case["pub_date"]),
        "precedential_statuses": "Published",
        "docket_numbers": case["docket"],
        "judges": panelists,
        "author_id": lead_author.id,
        "author": lead_author,
        "date_filed_is_approximate": False,
        "blocked_statuses": False,
        "neutral_citations": case["neutral_citation"],
        "download_urls": case["pdf_url"],
    }


def add_neutral_citations(tn_corpus):
    """Add neutral citations to our dataset

    :param tn_corpus: The case data.
    :type: dict
    :return: Our case data with neutral citations included.
    :type: dict
    """
    results = []
    for court in ['tennworkcompapp', 'tennworkcompcl']:
        reporter = 'TN WC App.' if court == "tennworkcompapp" else "TN WC"
        tn = [x for x in
                sorted(tn_corpus, key=lambda x: (x["pub_date"], x['label'])) if
                x['court'] == court]
        for key, group in itertools.groupby(tn, lambda x: x["pub_date"][:4]):
            count = 1
            for case in list(group):
                case['neutral_citation'] = "%s %s %s" % (key, reporter, count)
                results.append(case)
                count += 1
    return results

def import_tn_corpus(log, skip_until, dir):
    """Import TN Corpus

    :param log: Should we should logs
    :param skip_until: Label ID, if any, to process first
    :param dir: Location of pre-processed json
    :return: None
    """
    ready = False if skip_until else True

    if log:
        logging.getLogger().setLevel(logging.INFO)

    logging.info("Starting import")
    filepath = "%s/data.json" % dir
    tn_corpus = add_neutral_citations(json.loads(open(filepath, "r").read()))
    if not ready:
        case = [x for x in tn_corpus if x["label"] == int(skip_until)][0]
        logging.info(
            "Skipping until case %s labeled: %s", case["title"], case["label"]
        )

    for case in sorted(tn_corpus, key=lambda x: x["label"]):
        if case["label"] == int(skip_until):
            ready = True
        if not ready:
            continue
        logging.info(
            "Processing label:%s for case:%s", case["label"], case["title"]
        )
        pdf_path = [
            x
            for x in glob("%s/%s/*.pdf" % (dir, case["label"]))
            if "stamped" not in x
        ][0]
        pdf_data = open(pdf_path, "r").read()

        sha1_hash = sha1(force_bytes(pdf_data))
        ops = Opinion.objects.filter(sha1=sha1_hash)
        if len(ops) > 0:
            op = ops[0]
            logging.warn(
                "Document already in database. See: %s at %s"
                % (op.get_absolute_url(), op.cluster.case_name)
            )

        docket, opinion, cluster, citations, error = make_objects(
            make_item(case),
            Court.objects.get(pk=case["court"]),
            sha1(force_bytes(pdf_data)),
            open(pdf_path, "r").read(),
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
            opinion.pk, do_ocr=True, citation_jitter=True,
        )
        logging.info(
            "Successfully added Tennessee object cluster: %s", cluster.id
        )


class Command(VerboseCommand):
    help = "Import TN data corpus received from TN Workers Comp boards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-dir",
            help="The directory containing all the PDFs.",
            required=True,
        )
        parser.add_argument(
            "--log",
            action="store_true",
            default=False,
            help="Determine feedback level.",
        )
        parser.add_argument(
            "--skip-until", default=False, help="Skip until to process",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        import_tn_corpus(
            options["log"], options["skip_until"], options["input_dir"],
        )
