import os
from pathlib import Path
from typing import Dict

from juriscraper.pacer import DocketReport
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

from cl.lib.command_utils import VerboseCommand
from cl.recap.models import UPLOAD_TYPE, PacerHtmlFiles

report = DocketReport("cand")


def _write_anon_item_to_disk(pacer_file: PacerHtmlFiles) -> None:
    # Get the text and anonymize it
    with open(pacer_file.filepath.path, "r") as f:
        text = f.read()
    report._parse_text(text)
    try:
        anon_text = report.get_anonymized_text()
    except IndexError:
        print(f"Index error. Skipping: {pacer_file.filepath.path}")
        return

    # Save anonymized text to disk
    basename = os.path.basename(pacer_file.filepath.name)
    out = Path(f"/storage/sample-data/dockets/{basename[0:2]}/{basename[2:]}")
    out.parent.mkdir(exist_ok=True, parents=True)
    out.write_text(anon_text)


def make_html(options: Dict[str, int]) -> None:
    offset = options["offset"]
    pacer_files = PacerHtmlFiles.objects.filter(
        upload_type=UPLOAD_TYPE.DOCKET
    ).order_by("pk")[offset:]
    total = pacer_files.count()
    pacer_file_iterator = pacer_files.iterator()
    progress_bar = tqdm(
        total=total,
        dynamic_ncols=True,
        smoothing=0,
        initial=offset,
    )
    process_map(
        _write_anon_item_to_disk,
        pacer_file_iterator,
        max_workers=options["processes"],
        tqdm_class=progress_bar,
        chunksize=500,
        total=total,
    )


class Command(VerboseCommand):
    help = "Convert all HTML dockets to anonymized ones in a separate dir"

    def add_arguments(self, parser):
        parser.add_argument(
            "--processes",
            default=1,
            type=int,
            help="How many processes to run simultaneously",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        make_html(options)
