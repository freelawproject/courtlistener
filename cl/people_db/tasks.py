import subprocess
from tempfile import NamedTemporaryFile

from django.core.files import File

from cl.celery import app
from cl.people_db.models import FinancialDisclosure
from cl.search.models import THUMBNAIL_STATUSES


@app.task
def make_png_thumbnail_from_pdf(pk, width=350):
    """Create a png thumbnail from a financial disclosure PDF"""
    fd = FinancialDisclosure.objects.get(pk=pk)
    # Use a temporary location for the file, then save it to the model.
    with NamedTemporaryFile(prefix='financial_disclosure_',
                            suffix=".png") as tmp:
        convert = [
            'convert',
            # Only do the first page.
            '%s[0]' % fd.filepath.path,
            '-resize', '%s' % width,
            # This and the next line handle transparency problems
            '-background', 'white',
            '-alpha', 'remove',
            tmp.name,
        ]
        p = subprocess.Popen(convert, close_fds=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        stdout, stderr = p.communicate()

        if p.returncode != 0:
            fd.thumbnail_status = THUMBNAIL_STATUSES.FAILED
            fd.save()
            return fd.pk

        fd.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
        filename = '%s.thumb.%sw.png' % (fd.person.slug, width)
        fd.thumbnail.save(filename, File(tmp))

    return fd
