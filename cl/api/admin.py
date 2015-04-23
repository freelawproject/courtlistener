from django.contrib import admin
from tastypie.models import ApiKey

admin.site.unregister(ApiKey)
