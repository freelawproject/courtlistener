from django.contrib import admin
from oauth2_provider.admin import ApplicationAdmin
from oauth2_provider.models import get_application_model

Application = get_application_model()


class EditableSourceApplicationAdmin(ApplicationAdmin):
    """The toolkit's Application admin with ``registration_source`` editable."""

    readonly_fields = ("cimd_expires_at",)


admin.site.unregister(Application)
admin.site.register(Application, EditableSourceApplicationAdmin)
