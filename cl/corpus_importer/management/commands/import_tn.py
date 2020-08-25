import json
from glob import glob

from cl.lib.command_utils import VerboseCommand
import logging


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
    tn_corpus = json.loads(open(filepath, "r").read())

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


class Command(VerboseCommand):
    help = "Import TN Corpus"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            help="The json file containing the data to analyze.",
            default="cl/corpus_importer/tmp/data.json",
            # required=True,
        )
        parser.add_argument(
            "--input-dir",
            help="The directory containing all the PDFs.",
            default="utk_workerscomp",
            # required=True,
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
