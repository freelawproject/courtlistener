from django.db import models


# Flash is a jerk about only accepting these three rates.
# If an mp3 has a different sample rate, we downgrade it as necessary.
MP3_SAMPLE_RATES = (
    ('low', '11025'),
    ('medium', '22050'),
    ('high', '44100'),
)

class Audio(models.Model):
    SHA1 = models.CharField("SHA1 hash of the audio file",
        max_length=40)
    argued = models.DateField("the date the case was argued",
        blank=True,
        null=True)
    download_URL = models.URLField("the URL on the court website where the audio was originally scraped")
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
