from django.db.models.signals import m2m_changed
from alert.citations.tasks import update_citation_counts
from alert.search.models import Document

m2m_changed.connect(update_citation_counts, sender=Document.cases_cited.through)