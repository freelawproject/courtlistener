from collections.abc import Iterable
from typing import Any, ClassVar, cast

from django.db.models import Model, QuerySet

from cl.corpus_importer.state.merger import (
    Constant,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    OneToManyRelation,
    OneToOneRelation,
    Params,
    RelatedParams,
    Scrape,
    ThroughParameters,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.corpus_importer.state.tests import merger_test
from cl.people_db.factories import PersonFactory
from cl.people_db.models import Party, PartyType, Person
from cl.search.docket_sources import DocketSources
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
    TrialCourtData,
)
from cl.tests.cases import TestCase


class BaseMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()
        # pyrefly:ignore[bad-assignment]
        cls.docket_number: str = cls.docket.docket_number

    @merger_test(expected_query_count=1)
    def test_merger_creates_object(self) -> None:
        start_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("ABCDEFG")

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        r = TestMerger({}, params=None).merge()

        self.assertEqual(
            Docket.objects.count(),
            start_count + 1,
            "Docket should be created when it doesn't exist.",
        )
        self.assertEqual(r.success, True, "Merger should signal success.")
        self.assertEqual(
            r.create, True, "Merger should signal object was created."
        )
        self.assertEqual(
            r.update, False, "Merger should not signal object was updated."
        )
        self.assertEqual(
            ["Docket"], list(r.creates), "Merger should only create a Docket."
        )
        self.assertEqual(
            len(r.creates["Docket"]),
            1,
            "Exactly one Docket should be created.",
        )
        created_docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(created_docket.docket_number, "ABCDEFG")
        self.assertEqual(created_docket.court_id, self.court.id)
        self.assertEqual(created_docket.source, DocketSources.SCRAPER)

    @merger_test(expected_query_count=2)
    def test_merger_updates_docket(self) -> None:
        tc = self
        new_dn = self.docket_number + "New"
        start_docket_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court_id: str = Constant(self.court.id)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(new_dn)

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        r = TestMerger({}, params=None).merge()

        self.assertEqual(
            Docket.objects.count(),
            start_docket_count,
            "Docket should not be created when it exists.",
        )
        self.assertEqual(r.success, True, "Merger should signal success.")
        self.assertEqual(
            r.create, False, "Merger should not signal object was created."
        )
        self.assertEqual(
            r.update, True, "Merger should signal object was updated."
        )
        self.assertEqual(
            ["Docket"], list(r.updates), "Merger should only update a Docket."
        )
        self.assertEqual(
            len(r.updates["Docket"]),
            1,
            "Exactly one Docket should be updated.",
        )
        updated_pk = r.updates["Docket"].pop()
        self.assertEqual(
            updated_pk, self.docket.pk, "The correct Docket should be updated."
        )
        self.docket.refresh_from_db()
        self.assertEqual(
            self.docket.docket_number,
            new_dn,
            "The correct Docket should be updated.",
        )
        self.assertEqual(
            self.docket.source,
            DocketSources.SCRAPER,
        )
        self.assertEqual(
            self.docket.court_id,
            self.court.id,
        )

    @merger_test(expected_query_count=1)
    def test_mappings_called(self) -> None:
        map_calls = 0
        dn = "ABCDEFG"

        def test_mapping(i: dict[str, str], params) -> str:
            nonlocal map_calls
            map_calls += 1
            return dn

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Fn(test_mapping)(Scrape(dict), Params(Any))

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        r = TestMerger({}, params=None).merge()
        self.assertEqual(map_calls, 1)
        docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, dn)

    @merger_test(expected_query_count=3)
    def test_related_mergers_1to1(self) -> None:
        class TestRelatedMerger(
            Merger[
                dict[str, str],
                RelatedParams[None],
                OriginatingCourtInformation,
            ]
        ):
            model: ClassVar[type[Model]] = OriginatingCourtInformation

            docket_number: str = Scrape(dict)["sr"]

            @classmethod
            def get_existing(
                cls, d: dict[str, str], manager, params: None
            ) -> OriginatingCourtInformation | None:
                return None

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(self.docket_number + "New")
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    TestRelatedMerger,
                    Scrape(dict)["mctest"],
                )
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        i = {"mctest": {"sr": "test"}}
        result = TestMerger(i, params=None).merge()

        self.assertIn("OriginatingCourtInformation", result.creates)
        self.assertEqual(len(result.creates["OriginatingCourtInformation"]), 1)
        oci_pk = result.creates["OriginatingCourtInformation"].pop()
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, i["mctest"]["sr"])
        self.assertEqual(oci.docket.pk, result.creates["Docket"].pop())

    @merger_test(expected_query_count=6)
    def test_related_mergers_reverse_1to1_creates(self) -> None:
        """Does a reverse one-to-one relation, where the OneToOneField lives on the child, create the child pointing at the parent? The child merger does not declare the foreign key; the relation sets it."""
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            model: ClassVar[type[Model]] = TrialCourtData

            docket_number_trial: str = Scrape(dict)["dn"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str | None = Constant(tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
                TestRelatedMerger,
                Scrape(dict)["trial"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        result = TestMerger({"trial": {"dn": "CR-123"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("TrialCourtData", result.creates)
        self.docket.refresh_from_db()
        self.assertEqual(
            self.docket.trialcourtdata.docket_number_trial, "CR-123"
        )

    @merger_test(expected_query_count=5)
    def test_related_mergers_reverse_1to1_updates(self) -> None:
        """Does a reverse one-to-one relation update the row the parent already has instead of creating a second one?"""
        existing = TrialCourtData.objects.create(
            docket=self.docket, docket_number_trial="CR-000"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            model: ClassVar[type[Model]] = TrialCourtData

            docket_number_trial: str = Scrape(dict)["dn"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str | None = Constant(tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
                TestRelatedMerger,
                Scrape(dict)["trial"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        result = TestMerger({"trial": {"dn": "CR-999"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("TrialCourtData", result.creates)
        self.assertEqual(TrialCourtData.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.docket_number_trial, "CR-999")

    def test_one_to_one_relation_must_be_a_one_to_one_field(self) -> None:
        """A one-to-one spec reads its direction off the model, so the field it names has to be one-to-one in the first place. Is a spec pointed at anything else refused when the merger is defined?"""

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry

            description: str = Scrape(dict)["df"]

        with self.assertRaises(TypeError):

            class TestMerger(Merger[dict[str, Any], None, Docket]):
                model: ClassVar[type[Model]] = Docket

                docket_entries: list[DocketEntry] = OneToOneRelation(
                    TestRelatedMerger,
                    cast(AttributeMerger, Scrape(Any)),
                )

    @merger_test(expected_query_count=5)
    def test_related_mergers_child(self) -> None:
        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry

            description: str = Scrape(dict)["df"]

            def query(self) -> QuerySet[DocketEntry]:
                return DocketEntry.objects.none()

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(self.docket_number + "New")
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                Scrape(dict)["mctest"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        i = {
            "mctest": [
                {"df": "test1"},
                {"df": "test2"},
                {"df": "test3"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertIn("DocketEntry", result.creates)
        self.assertEqual(len(result.creates["DocketEntry"]), 3)
        des = list(
            DocketEntry.objects.filter(pk__in=result.creates["DocketEntry"])
        )
        self.assertEqual(len(des), 3)
        self.assertEqual(
            set(de.description for de in des),
            set(mctest["df"] for mctest in i["mctest"]),
        )
        self.assertEqual(
            set(de.docket.pk for de in des), set(result.creates["Docket"])
        )

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_simple(self) -> None:
        """Does a plain (no-through) many-to-many relation create the targets and link them to the parent? Uses batched candidate lookups so the bulk-linking path is exercised."""

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            model: ClassVar[type[Model]] = Person

            name_first: str = Scrape(dict)["first"]
            name_last: str = Scrape(dict)["last"]
            slug: str = Scrape(dict)["slug"]
            key = ["slug"]

            @classmethod
            def candidates(
                cls, parent: Model, params: RelatedParams[None]
            ) -> QuerySet[Person]:
                return Person.objects.filter(empanelled_dockets=parent)

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("M2M-SIMPLE")
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                Scrape(dict)["panel"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        i = {
            "panel": [
                {"first": "Jane", "last": "Doe", "slug": "jane-doe-m2m"},
                {"first": "John", "last": "Roe", "slug": "john-roe-m2m"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertIn("Person", result.creates)
        self.assertEqual(len(result.creates["Person"]), 2)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(
            set(docket.panel.values_list("name_last", flat=True)),
            {"Doe", "Roe"},
        )

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_through(self) -> None:
        """Does a many-to-many relation with a `through` model create the targets, link them to the parent, and populate the through row's own fields from the same scrape?"""

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("M2M-THROUGH")
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        i = {
            "parties": [
                {"name": "Alice", "type": "Plaintiff"},
                {"name": "Bob", "type": "Defendant"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertIn("Party", result.creates)
        self.assertEqual(len(result.creates["Party"]), 2)
        self.assertIn("PartyType", result.creates)
        self.assertEqual(len(result.creates["PartyType"]), 2)

        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(
            set(docket.parties.values_list("name", flat=True)),
            {"Alice", "Bob"},
        )
        self.assertEqual(
            {
                (pt.party.name, pt.name)
                for pt in PartyType.objects.filter(docket=docket)
            },
            {("Alice", "Plaintiff"), ("Bob", "Defendant")},
        )

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_simple_disassociate(self) -> None:
        """Does DISASSOCIATE on a plain many-to-many remove stale associations while keeping the objects themselves?"""
        stale = PersonFactory.create()
        self.docket.panel.add(stale)
        tc = self

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            model: ClassVar[type[Model]] = Person
            key: ClassVar[Iterable[str]] = ["slug"]

            name_first: str = Scrape(dict)["first"]
            name_last: str = Scrape(dict)["last"]
            slug: str = Scrape(dict)["slug"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                Scrape(dict)["panel"],
                strategy=ManyStrategy.DISASSOCIATE,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {
            "panel": [
                {"first": "Jane", "last": "Doe", "slug": "jane-doe-dis"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.docket.refresh_from_db()
        self.assertTrue(
            Person.objects.filter(pk=stale.pk).exists(),
            "DISASSOCIATE must not delete the stale person.",
        )
        self.assertEqual(
            set(self.docket.panel.values_list("name_last", flat=True)),
            {"Doe"},
            "The stale association should be removed.",
        )

    @merger_test(expected_query_count=10)
    def test_related_mergers_m2m_through_disassociate(self) -> None:
        """Does DISASSOCIATE on a through many-to-many prune the stale through rows while keeping the related objects themselves?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
                strategy=ManyStrategy.DISASSOCIATE,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {"parties": [{"name": "Alice", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.docket.refresh_from_db()
        self.assertTrue(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "DISASSOCIATE must not delete the stale party itself.",
        )
        self.assertFalse(
            PartyType.objects.filter(
                docket=self.docket, party=stale_party
            ).exists(),
            "The stale party's link to the docket should be removed.",
        )
        self.assertEqual(
            set(self.docket.parties.values_list("name", flat=True)),
            {"Alice"},
        )

    @merger_test(expected_query_count=16)
    def test_related_mergers_m2m_through_replace_deletes(self) -> None:
        """Characterization: does REPLACE on a through many-to-many delete the stale related objects outright?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {"parties": [{"name": "Alice", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "REPLACE deletes stale related objects outright.",
        )

    @merger_test(expected_query_count=4)
    def test_related_mergers_child_replace_keeps_rows_on_invalid_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's input is invalid? The child gives up before looking anything up, so the row it would have matched isn't known and can't be pruned safely."""
        stale = DocketEntry.objects.create(
            docket=self.docket, description="Stale"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry
            key: ClassVar[Iterable[str]] = ["description"]

            description: str = Scrape(dict)["df"]

            @staticmethod
            def validate(scrape: dict[str, str]) -> bool:
                return scrape["df"] != "Invalid"

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                Scrape(dict)["entries"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {"entries": [{"df": "Fresh"}, {"df": "Invalid"}]}
        result = TestMerger(i, params=None).merge()

        self.assertFalse(result.success)
        self.assertTrue(
            DocketEntry.objects.filter(pk=stale.pk).exists(),
            "A failed child merge must not let REPLACE delete existing rows.",
        )
        self.assertEqual(
            set(
                self.docket.docket_entries.values_list(
                    "description", flat=True
                )
            ),
            {"Stale", "Fresh"},
        )

    @merger_test(expected_query_count=3)
    def test_related_mergers_m2m_replace_keeps_rows_on_ambiguous_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's lookup matches several rows? The merger can't pick one, so it never learns which row belongs to this scrape."""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        Party.objects.create(name="Ambiguous")
        Party.objects.create(name="Ambiguous")
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {"parties": [{"name": "Ambiguous", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertFalse(result.success)
        self.assertTrue(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "An ambiguous child lookup must not let REPLACE delete existing "
            "rows.",
        )
        self.assertTrue(
            PartyType.objects.filter(
                docket=self.docket, party=stale_party
            ).exists(),
            "An ambiguous child lookup must not let REPLACE prune existing "
            "through rows.",
        )

    @merger_test(expected_query_count=1)
    def test_merger_subclassing(self) -> None:
        class TestMerger(Merger[dict[str, str], dict[str, Any], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("ABCDEFG")

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        class TestMerger2(TestMerger):
            court: Court = Constant(self.court)
            docket_number: str = Constant("ABCDEFGH")
            assigned_to_str: str = Params(dict)["assigned_to_str"]

        ats = "test"
        result = TestMerger2({}, params={"assigned_to_str": ats}).merge()

        self.assertIn("Docket", result.creates)
        self.assertEqual(len(result.creates["Docket"]), 1)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, "ABCDEFGH")
        self.assertEqual(docket.source, DocketSources.SCRAPER)
        self.assertEqual(docket.assigned_to_str, ats)
