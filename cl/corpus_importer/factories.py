import string

import factory
from factory import Faker
from factory.fuzzy import FuzzyText


class CitationFactory(factory.DictFactory):
    cite = Faker("citation")


class CaseLawCourtFactory(factory.DictFactory):
    name = Faker("court_name")


class CaseBodyFactory(factory.DictFactory):
    data = (
        '<casebody firstpage="1" lastpage="2">\n <otherdate '
        'id="Ail">March 3, 2009.</otherdate>  <opinion '
        'type="majority"><author id="b123-14">Cowin, J.</author>Everybody '
        "wins.</opinion>\n</casebody> "
    )


class CaseLawFactory(factory.DictFactory):
    citations = factory.List(
        [factory.SubFactory(CitationFactory) for _ in range(2)]
    )
    id = Faker("random_id")
    url = Faker("url")
    name = Faker("case_name", full=True)
    name_abbreviation = Faker("case_name")
    decision_date = Faker("date")
    court = factory.SubFactory(CaseLawCourtFactory)
    casebody = factory.SubFactory(CaseBodyFactory)
    docket_number = Faker("federal_district_docket_number")


class RssDocketEntryDataFactory(factory.DictFactory):
    date_filed = Faker("date_object")
    description = ""
    document_number = Faker("pyint", min_value=1, max_value=100)
    pacer_doc_id = Faker("random_id_string")
    pacer_seq_no = Faker("random_id_string")
    short_description = Faker("text", max_nb_chars=40)


class RssDocketDataFactory(factory.DictFactory):
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    case_name = Faker("case_name")
    docket_entries = factory.List(
        [factory.SubFactory(RssDocketEntryDataFactory)]
    )
    docket_number = Faker("federal_district_docket_number")
    office = Faker("pyint", min_value=1, max_value=100)
    chapter = Faker("pyint", min_value=1, max_value=100)
    trustee_str = Faker("text", max_nb_chars=15)
    type = Faker("text", max_nb_chars=8)
    pacer_case_id = Faker("random_id_string")
