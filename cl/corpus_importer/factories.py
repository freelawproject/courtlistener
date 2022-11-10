import factory
from factory import Faker


class CitationFactory(factory.DictFactory):
    cite = Faker("random_citation")


class CaseLawCourtFactory(factory.DictFactory):
    name = Faker("court_name")


class CaseBodyFactory(factory.DictFactory):
    data = '<casebody firstpage="1" lastpage="2">\n  <opinion type="majority">Everybody wins.</opinion>\n</casebody>'


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
