from factory import Faker
from factory.django import DjangoModelFactory, FileField

from cl.audio.models import Audio
from cl.search.factories import DocketParentMixin
from cl.search.models import SOURCES


class AudioFactory(DjangoModelFactory):
    class Meta:
        model = Audio

    id = Faker("random_id")
    source = Faker("random_element", elements=SOURCES)
    case_name = Faker("case_name")
    sha1 = Faker("sha1")
    download_url = Faker("url")
    local_path_mp3 = FileField(upload_to="/tmp/audio")
    local_path_original_file = FileField(upload_to="/tmp/audio/")


class AudioWithParentsFactory(AudioFactory, DocketParentMixin):
    """Make an Audio with Docket parents"""

    pass
