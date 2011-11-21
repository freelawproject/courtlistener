from haystack.indexes import CharField
from haystack.indexes import DateField
from haystack.indexes import RealTimeSearchIndex
from haystack import site
from alert.search.models import Document

class DocumentIndex(RealTimeSearchIndex):
    text = CharField(document=True, use_template=True)
    dateFiled = DateField(model_attr='dateFiled', null=True)
    court = CharField(model_attr='court__shortName', faceted=True)
    caseName = CharField(model_attr='citation__caseNameFull', boost=1.25)
    docketNumber = CharField(model_attr='citation__docketNumber', null=True)
    westCite = CharField(model_attr='citation__westCite', null=True)
    lexisCite = CharField(model_attr='citation__lexisCite', null=True)
    status = CharField(model_attr='documentType', faceted=True, boost=1.25)
    caseNumber = CharField(use_template=True, null=True, boost=1.25)

    def index_queryset(self):
        """Used when the entire index for model is updated."""

        # TODO: Does this work on LARGE sets of documents? 
        return Document.objects.all()


site.register(Document, DocumentIndex)
