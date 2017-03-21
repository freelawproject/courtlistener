from collections import Counter

from django.core.management.base import BaseCommand

from cl.scrapers.tasks import get_page_count
from cl.search.models import RECAPDocument


class Command(BaseCommand):
    help = 'Calculate page counts for items in RECAP'

    def handle(self, *args, **options):
        raw_input(
            "This is a very primitive script that has serious performance "
            "issues with large datasets. Press any key to proceed anyway. "
            "Otherwise, press CTRL+C to exit."
        )
        cnt = Counter()
        for rd in RECAPDocument.objects.all():
            try:
                path = rd.filepath_local.path
            except ValueError:
                cnt['no_file'] += 1
            else:
                extension = path.split('.')[-1]
                count = get_page_count(path, extension)
                rd.page_count = count
                rd.save(do_extraction=False, index=False)
                cnt['successes'] += 1
                if count is not None:
                    cnt['total_pages'] += count

        print cnt
