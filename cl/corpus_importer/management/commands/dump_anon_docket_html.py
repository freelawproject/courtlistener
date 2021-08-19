import os
from pathlib import Path
from typing import Dict

from juriscraper.pacer import DocketReport

from cl.lib.command_utils import VerboseCommand
from cl.recap.models import UPLOAD_TYPE, PacerHtmlFiles


def make_html(options: Dict[str:str]) -> None:
    pacer_files = (
        PacerHtmlFiles.objects.filter(upload_type=UPLOAD_TYPE.DOCKET)
        .order_by("pk")
        .iterator()
    )
    report = DocketReport("cand")
    for pacer_file in pacer_files:
        # Get the text and anonymize it
        with open(pacer_file.filepath.path, "r") as f:
            text = f.read()
        report._parse_text(text)
        anon_text = report.get_anonymized_text()

        # Save anonymized text to disk
        basename = os.path.basename(pacer_file.filepath.name)
        out = Path(
            f"/storage/sample-data/dockets/{basename[0:2]}/{basename[2:]}"
        )
        out.parent.mkdir(exist_ok=True, parents=True)
        out.write_text(anon_text)


class Command(VerboseCommand):
    help = "Convert all HTML dockets to anonymized ones in a separate dir"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        make_html(options)
