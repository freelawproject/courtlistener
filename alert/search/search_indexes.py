import datetime
from haystack.indexes import
from haystack import site
from alert.search.models import Citation
from alert.search.models import Document

class DocumentIndex(SearchIndex):
    text = CharField(document=True, use_template=True)
    dateFiled =
    author = CharField(model_attr='user')
    pub_date = DateTimeField(model_attr='pub_date')

    def index_queryset(self):
        """Used when the entire index for model is updated."""
        return Document.objects.all()


site.register(Document, DocumentIndex)


    dateFiled = models.DateField("the date filed by the court",
        blank=True,
        null=True,
        db_index=True)
    court = models.ForeignKey(Court,
        verbose_name="the court where the document was filed",
        db_index=True)
    citation = models.ForeignKey(Citation,
        verbose_name="the citation information for the document",
        blank=True,
        null=True)
    download_URL = models.URLField("the URL on the court website where the document was originally scraped",
        verify_exists=False,
        db_index=True)
    time_retrieved = models.DateTimeField("the exact date and time stamp that the document was placed into our database",
        auto_now_add=True,
        editable=False)
    local_path = models.FileField("the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to=make_pdf_upload_path,
        blank=True)
    documentPlainText = models.TextField("plain text of the document after extraction from the PDF",
        blank=True)
    documentHTML = models.TextField("HTML of the document",
        blank=True)
    documentType = models.CharField("the type of document, as described by document_types.txt",
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES)
    date_blocked = models.DateField('original block date',
        blank=True,
        null=True)
    blocked = models.BooleanField('block crawlers for this document',
        db_index=True,
        default=False)
