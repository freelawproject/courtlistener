from factory import Faker
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice

from cl.audio.models import Audio
from cl.search.factories import DocketParentMixin
from cl.search.models import SOURCES


class AudioFactory(DjangoModelFactory):
    class Meta:
        model = Audio

    source = FuzzyChoice(SOURCES.NAMES, getter=lambda c: c[0])
    case_name = Faker("case_name")
    sha1 = Faker("sha1")
    download_url = Faker("url")
    local_path_mp3 = FileField(upload_to="/tmp/audio")
    local_path_original_file = FileField(upload_to="/tmp/audio/")


class AudioWithParentsFactory(AudioFactory, DocketParentMixin):
    """Make an Audio with Docket parents"""

    pass
