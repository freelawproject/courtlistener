
from django.db import models

class SearchQuery(models.Model):
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)

    query_time_ms = models.IntegerField()

    get_params = models.CharField(max_length=255)

    date_modified = models.DateTimeField(auto_now=True, db_index=True)
