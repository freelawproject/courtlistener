from django.contrib import admin
from cl.judges.models import (
    Education, School, Judge, Position, Politician, RetentionEvent, Career,
    Title, Race, PoliticalAffiliation, Source, ABARating)

admin.site.register(Judge)
admin.site.register(Education)
admin.site.register(School)
admin.site.register(Position)
admin.site.register(Politician)
admin.site.register(PoliticalAffiliation)
admin.site.register(RetentionEvent)
admin.site.register(Career)
admin.site.register(Title)
admin.site.register(Race)
admin.site.register(Source)
admin.site.register(ABARating)
