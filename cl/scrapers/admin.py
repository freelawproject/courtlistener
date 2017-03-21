from django.contrib import admin

from cl.scrapers.models import UrlHash, ErrorLog, RECAPLog, PACERFreeDocumentLog


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    readonly_fields = ('log_time', 'log_level', 'court', 'message',)
    list_display = ('log_level', 'log_time', 'court')
    list_filter = ('court',)


@admin.register(RECAPLog)
class RECAPLogAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'date_started', 'date_completed')
    list_filter = ('status',)
    list_editable = ('status',)
    date_hierarchy = 'date_started'
    ordering = ('-date_started',)


@admin.register(PACERFreeDocumentLog)
class PACERFreeDocumentLogAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'court_id', 'status', 'date_started',
                    'date_completed', 'date_queried')
    list_filter = ('status', 'court__jurisdiction')
    list_editable = ('status',)
    date_hierarchy = 'date_queried'
    ordering = ('-date_started',)


admin.site.register(UrlHash)
