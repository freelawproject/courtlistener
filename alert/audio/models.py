# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.
from django.db import models
from django.utils.text import get_valid_filename
# from search.models import Document


# Flash is a jerk about only accepting these three rates.
# If an mp3 has a different sample rate, we downgrade it as necessary.
MP3_SAMPLE_RATES = (
    ('low',    '11025'),
    ('medium', '22050'),
    ('high',   '44100'),
)


def make_upload_path(instance, filename):
    """Return a string like audio/2010/08/13/foo_v._var.mp3, with the date set
    as the dateFiled for the case."""

    # get the doc that has this audio file as a foreign key.
    doc = Document.object.get(audio = instance.id)

    # this code NOT cross platform. Use os.path.join or similar to fix.
    return 'audio/' + doc.dateFiled.strftime("%Y/%m/%d/") + \
        get_valid_filename(filename)


class Audio(models.Model):
    SHA1 = models.CharField("SHA1 hash of the audio file",
        max_length=40)
    argued = models.DateField("the date the case was argued",
        blank=True,
        null=True)
    download_URL = models.URLField("the URL on the court website where the audio was originally scraped",
        verify_exists=False)
    time_retrieved = models.DateTimeField("the exact date and time stamp that the audio was placed into our database",
        auto_now_add=True,
        editable=False)
    local_path_mp3 = models.FileField("the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to=make_upload_path,
        blank=True)
    local_path_ogg = models.FileField("the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to=make_upload_path,
        blank=True)
    length = models.TimeField("the length of the file")
    sample_rate_mp3 = models.IntegerField("the bitrate of the MP3",
        blank=True,
        choices=MP3_SAMPLE_RATES)

    def __unicode__(self):
        return self.local_path_mp3

    class Meta:
        db_table = "Audio"
        ordering = ["-time_retrieved"]
