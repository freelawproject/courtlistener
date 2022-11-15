import factory
from factory import Faker


class CitationFactory(factory.DictFactory):
    cite = Faker("citation")


class CaseLawCourtFactory(factory.DictFactory):
    name = Faker("court_name", known=True)


class CaseBodyFactory(factory.DictFactory):
    data = '<casebody firstpage="1" lastpage="2">\n <otherdate id="Ail">March 3, 2009.</otherdate>  <opinion type="majority"><author id="b123-14">Cowin, J.</author>Everybody wins.</opinion>\n</casebody>'


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
