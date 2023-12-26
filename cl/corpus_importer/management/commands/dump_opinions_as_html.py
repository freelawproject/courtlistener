import os
from pathlib import Path

from django.db.models import Q
from django.template.loader import render_to_string

from cl.lib.argparse_types import readable_dir
from cl.lib.command_utils import VerboseCommand
from cl.search.models import Opinion


class Command(VerboseCommand):
    help = "A simple script to serialize all opinions to disk as HTML"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-directory",
            type=readable_dir,
            required=True,
            help="A directory to place the generated data.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        ops = Opinion.objects.exclude(
            Q(html="") | Q(html=None),
            Q(html_lawbox="") | Q(html_lawbox=None),
            Q(html_columbia="") | Q(html_columbia=None),
        )

        for op in ops.iterator():
            content = render_to_string("simple_opinion.html", {"o": op})
            output_dir = os.path.join(
                options["output_directory"],
                str(op.cluster.date_filed.year),
                str(op.cluster.date_filed.month),
                str(op.cluster.date_filed.day),
            )
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            output_path = os.path.join(output_dir, f"{op.pk}.html")
            with open(output_path, "w") as f:
                f.write(content.encode())
