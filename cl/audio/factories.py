from factory import Faker, post_generation
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

    """
    These hooks are necessary to make this factory compatible with the
    `make_dev_command`. by delegating the file creation to the hooks, we prevent
    the model from trying to use our storage settings when the field is not
    explicitly requested.
    """

    @post_generation
    def local_path_mp3(self, create, extracted, **kwargs):
        if extracted:
            self.local_path_mp3 = extracted
        elif kwargs:
            # Factory Boy uses the `evaluate` method of each field to calculate
            # values for object creation. The FileField class only requires the
            # extra dictionary to create the stub django file.
            #
            # Learn more about FactoryBoy's `FileField` class:
            # https://github.com/FactoryBoy/factory_boy/blob/ac49fb40ec424276c3cd3ca0925ba99a626f05f7/factory/django.py#L249
            self.local_path_mp3 = FileField().evaluate(None, None, kwargs)

    @post_generation
    def local_path_original_file(self, create, extracted, **kwargs):
        if extracted:
            self.local_path_original_file = extracted
        elif kwargs:
            self.local_path_original_file = FileField().evaluate(
                None, None, kwargs
            )

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Save again the instance if creating and at least one hook ran."""
        if create and results:
            # Some post-generation hooks ran, and may have modified the instance.
            instance.save(
                update_fields=["local_path_mp3", "local_path_original_file"],
            )


class AudioWithParentsFactory(AudioFactory, DocketParentMixin):
    """Make an Audio with Docket parents"""

    pass
