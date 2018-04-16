import os

from django.db.models import Q
from django.template.loader import render_to_string

from cl.lib.argparse_types import readable_dir
from cl.lib.command_utils import VerboseCommand
from cl.lib.db_tools import queryset_generator
from cl.lib.utils import mkdir_p
from cl.search.models import Opinion


class Command(VerboseCommand):
    help = "A simple script to serialize all opinions to disk as HTML"

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-directory',
            type=readable_dir,
            required=True,
            help='A directory to place the generated data.',
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        ops = queryset_generator(Opinion.objects.exclude(
            Q(html='') | Q(html=None),
            Q(html_lawbox='') | Q(html_lawbox=None),
            Q(html_columbia='') | Q(html_columbia=None),
        ))

        for op in ops:
            content = render_to_string('simple_opinion.html', {
                'o': op,
            })
            output_dir = os.path.join(
                options['output_directory'],
                op.cluster.date_filed.year,
                op.cluster.date_filed.month,
                op.cluster.date_filed.day,
            )
            mkdir_p(output_dir)
            output_path = os.path.join(output_dir, '%s.html' % op.pk)
            with open(output_path, 'w') as f:
                f.write(content.encode('utf-8'))
