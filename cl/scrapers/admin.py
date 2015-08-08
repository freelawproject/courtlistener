from django.contrib import admin
from cl.scrapers.models import UrlHash, ErrorLog


class ErrorLogAdmin(admin.ModelAdmin):
    readonly_fields = ('log_time', 'log_level', 'court', 'message',)
    list_display = ('log_level', 'log_time', 'court')
    list_filter = ('court',)


admin.site.register(UrlHash)
admin.site.register(ErrorLog, ErrorLogAdmin)
