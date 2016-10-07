import pandas as pd
from django.core.management import BaseCommand

from cl.search.models import OpinionsCited, Opinion
from cl.search.tasks import add_or_update_opinions


def load_csv(csv_location):
    data = pd.read_csv(csv_location, delimiter=',', dtype={
        'citing': int,
        'cited': int,
    })
    return data, len(data.index)


def process_citations(data, debug):
    """Walk through the citations and add them one at a time.
    """
    updated_ids = set()
    for index, item in data.iterrows():
        print("\nAdding citation from %s to %s" % (item['citing'],
                                                   item['cited']))
        try:
            cite = OpinionsCited.objects.get(
                citing_opinion_id=item['citing'],
                cited_opinion_id=item['cited'],
            )
            msg = "Citation already exists. Doing nothing:\n"
        except OpinionsCited.DoesNotExist:
            cite = OpinionsCited(citing_opinion_id=item['citing'],
                                 cited_opinion_id=item['cited'])
            msg = "Created new citation:\n"
            if not debug:
                cite.save()
                updated_ids.add(cite.citing_opinion.pk)
        try:
            print(
                "  %s"
                "    %s: %s\n"
                "    From: %s\n"
                "    To:   %s\n" % (msg, cite.pk, cite, cite.citing_opinion,
                                    cite.cited_opinion)
            )
        except Opinion.DoesNotExist:
            print("  Unable to create citation. Underlying Opinion doesn't "
                  "exist.")

    print("\nUpdating Solr...")
    if not debug:
        add_or_update_opinions(updated_ids)
    print("Done.")


class Command(BaseCommand):
    help = 'Add the citations in the manual citations csv, if they do not ' \
           'already exist.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help='Only pretend to add the citations. Save nothing.'
        )
        parser.add_argument(
            '--csv',
            required=True,
            help="The absolute path to the CSV containing the citations to "
                 "add.",
        )

    def handle(self, *args, **options):
        data, length = load_csv(options['csv'])
        print("Found %s citations to add." % length)
        process_citations(data, options['debug'])
