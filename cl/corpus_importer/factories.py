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


class FreeOpinionRowDataFactory(factory.DictFactory):
    case_name = Faker("case_name")
    cause = Faker("text", max_nb_chars=8)
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    date_filed = Faker("date_object")
    description = Faker("text", max_nb_chars=10)
    docket_number = Faker("federal_district_docket_number")
    document_number = Faker("pyint", min_value=1, max_value=100)
    nature_of_suit = Faker("text", max_nb_chars=8)
    pacer_case_id = Faker("random_id_string")
    pacer_doc_id = Faker("random_id_string")
    pacer_seq_no = Faker("pyint", min_value=1, max_value=10000)


class CaseQueryDataFactory(factory.DictFactory):
    assigned_to_str = Faker("name_female")
    case_name = Faker("case_name")
    case_name_raw = Faker("case_name")
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    date_filed = Faker("date_object")
    date_last_filing = Faker("date_object")
    date_terminated = Faker("date_object")
    docket_number = Faker("federal_district_docket_number")
