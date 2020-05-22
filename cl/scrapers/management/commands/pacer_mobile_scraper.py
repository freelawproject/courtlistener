# coding=utf-8
from __future__ import print_function

from cl.alerts.models import DocketAlert
from cl.alerts.tasks import crawl_pacer_mobile_page
from cl.lib.command_utils import VerboseCommand
from cl.search.models import Docket


class Command(VerboseCommand):
    help = "Scrape PACER mobile query page"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        while True:
            docket_ids = set(
                DocketAlert.objects.values_list("docket", flat=True)
            )
            for i, docket_id in enumerate(docket_ids):
                d = Docket.objects.get(pk=docket_id)

                # TODO: Add tricky timing logic here from earlier PR
                crawl_pacer_mobile_page.delay(d.pk)
