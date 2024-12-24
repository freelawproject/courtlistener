from django.core.management.base import BaseCommand

from cl.sitemaps_infinite.sitemap_generator import generate_urls_chunk


class Command(BaseCommand):
    help = """The command starts or continues the sitemap urls generation. 
    The place where the generation was stopped last time is saved into the redis cache and then loaded when the command starts"""

    def handle(self, *args, **options):
        generate_urls_chunk()
