from django.contrib import admin
from alert.scrapers.models import urlToHash, ErrorLog


class ErrorLogAdmin(admin.ModelAdmin):
    readonly_fields = ('log_time', 'log_level', 'court')
    list_display = ('log_level', 'log_time', 'court')


admin.site.register(urlToHash)
admin.site.register(ErrorLog, ErrorLogAdmin)
