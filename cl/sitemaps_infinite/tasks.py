import logging

from celery import shared_task

from cl.sitemaps_infinite.sitemap_generator import generate_urls_chunk

logger = logging.getLogger(__name__)


@shared_task
def generate_sitemaps_task() -> None:
    logger.info("Starting sitemaps pregeneration Celery task.")
    generate_urls_chunk()
    logger.info("Finished sitemaps pregeneration Celery task.")
