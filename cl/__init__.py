# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery_init import app as celery_app
