from sitemaps_infinite.conf import CELERY_TASK_REPETITION

from cl.celery_init import app
from cl.sitemaps_infinite.sitemap_generator import generate_urls_chunk

if CELERY_TASK_REPETITION:
    # use `on_after_finalize` to setup periodic task because `on_after_configure` is sent before this task file is discovered
    @app.on_after_finalize.connect
    def setup_periodic_tasks(sender, **kwargs):
        sender.add_periodic_task(
            CELERY_TASK_REPETITION,
            sitemap_generation_task,
            name="sitemaps.tasks.GenerateSitemap-periodic",
        )

    @app.task(name="sitemaps.tasks.GenerateSitemap", ignore_result=True)
    def sitemap_generation_task() -> None:
        """Generate next sitemap chunk."""
        generate_urls_chunk()
