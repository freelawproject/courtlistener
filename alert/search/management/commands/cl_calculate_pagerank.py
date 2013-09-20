__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.tasks import do_pagerank

class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def handle(self, *args, **options):
        do_pagerank()
