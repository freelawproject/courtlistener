from django.contrib import admin
from alert.scrapers.models import urlToHash, ErrorLog

admin.site.register(urlToHash)
admin.site.register(ErrorLog)
