from factory import Faker
from factory.django import DjangoModelFactory

from cl.scrapers.models import PACERFreeDocumentRow


class PACERFreeDocumentRowFactory(DjangoModelFactory):
    class Meta:
        model = PACERFreeDocumentRow

    docket_number = Faker("federal_district_docket_number")
    case_name = Faker("case_name")
    date_filed = Faker("date_object")
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)
    pacer_seq_no = Faker("pyint", min_value=10_000, max_value=200_000)
    document_number = Faker("pyint", min_value=1, max_value=100)
    description = Faker("text", max_nb_chars=75)
    nature_of_suit = Faker("text", max_nb_chars=50)
    cause = Faker("text", max_nb_chars=50)
    error_msg = Faker("text", max_nb_chars=50)
