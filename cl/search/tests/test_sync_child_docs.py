from unittest import mock

from celery.exceptions import Retry

from cl.search.management.commands.sync_child_docs import (
    get_comparable_fields,
    get_out_of_sync_fields,
    get_sync_config,
)
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import (
    get_parent_fields_for_children,
    handle_incomplete_ubq_update,
)
from cl.tests.cases import SimpleTestCase


def make_ubq_response(
    total: int = 0, version_conflicts: int = 0, failures: list | None = None
):
    """Build a stand-in for an UpdateByQuery response.

    :param total: The number of documents the update matched.
    :param version_conflicts: The number of version conflicts hit.
    :param failures: The failures reported by Elasticsearch.
    :return: An object exposing the response attributes we check.
    """
    return mock.Mock(
        total=total,
        version_conflicts=version_conflicts,
        failures=failures if failures is not None else [],
    )


def make_task(retries: int = 0):
    """Build a stand-in for the celery task `self`.

    :param retries: The number of retries already attempted.
    :return: A Mock whose `retry()` returns a raisable Retry.
    """
    task = mock.Mock()
    task.request.retries = retries
    task.retry.return_value = Retry()
    return task


class ParentFieldsForChildrenTest(SimpleTestCase):
    """Tests for resolving the parent values children should denormalize."""

    def setUp(self) -> None:
        self.config = get_sync_config(SEARCH_TYPES.RECAP)
        self.docket = Docket(
            pk=73623037,
            case_name="WaitBusters LLC v. Oracle Corporation",
            docket_number="1:26-cv-01955",
            nature_of_suit="830 Patent",
            cause="35:271 Patent Infringement",
            jury_demand="Plaintiff",
        )
        self.comparable_fields = get_comparable_fields(
            self.config.child_doc_class,
            [
                field_name
                for field_names in self.config.fields_map.values()
                for field_name in field_names
            ],
        )

    def get_expected_fields(self) -> dict:
        """Resolve the fields the docket should push onto its children.

        :return: A dict of Elasticsearch field name to expected value.
        """
        return get_parent_fields_for_children(
            self.config.parent_doc_class,
            self.docket,
            self.config.fields_to_update,
            self.config.fields_map,
        )

    def test_maps_model_fields_onto_elasticsearch_field_names(self) -> None:
        """Are model field values resolved under their ES field names?"""
        fields = self.get_expected_fields()
        self.assertEqual(fields["suitNature"], "830 Patent")
        self.assertEqual(fields["cause"], "35:271 Patent Infringement")
        self.assertEqual(fields["juryDemand"], "Plaintiff")
        self.assertEqual(
            fields["caseName"], "WaitBusters LLC v. Oracle Corporation"
        )
        self.assertEqual(fields["docketNumber"], "1:26-cv-01955")

    def test_omits_model_field_names_that_arent_indexed(self) -> None:
        """Are model field names absent when they map to a different ES name?"""
        fields = self.get_expected_fields()
        for model_field in ["nature_of_suit", "jury_demand", "case_name"]:
            with self.subTest(model_field=model_field):
                self.assertNotIn(model_field, fields)

    def test_detects_the_drift_reported_in_issue_7965(self) -> None:
        """Is a child missing its docket's fields reported as out of sync?

        The two RECAPDocuments that made docket 73623037 match
        `-suitNature:Patent` were missing suitNature, cause and juryDemand while
        holding the right caseName and docketNumber.
        """
        expected_fields = self.get_expected_fields()
        stale_child = {
            "caseName": "WaitBusters LLC v. Oracle Corporation",
            "docketNumber": "1:26-cv-01955",
        }
        self.assertEqual(
            get_out_of_sync_fields(
                stale_child, expected_fields, self.comparable_fields
            ),
            ["suitNature", "cause", "juryDemand"],
        )

    def test_reports_nothing_for_a_child_in_sync(self) -> None:
        """Is a child holding every expected value reported as clean?"""
        expected_fields = self.get_expected_fields()
        healthy_child = {
            field_name: value
            for field_name, value in expected_fields.items()
            if isinstance(value, str)
        }
        self.assertEqual(
            get_out_of_sync_fields(
                healthy_child, expected_fields, self.comparable_fields
            ),
            [],
        )

    def test_treats_missing_and_empty_values_as_equal(self) -> None:
        """Is an absent value equivalent to an empty one?

        Neither puts a term in the index, so neither should look like drift.
        """
        self.assertEqual(
            get_out_of_sync_fields({}, {"suitNature": ""}, {"suitNature"}),
            [],
        )
        self.assertEqual(
            get_out_of_sync_fields(
                {"suitNature": None}, {"suitNature": None}, {"suitNature"}
            ),
            [],
        )

    def test_reports_a_value_the_parent_no_longer_has(self) -> None:
        """Is a child keeping a value its parent dropped reported as drift?"""
        self.assertEqual(
            get_out_of_sync_fields(
                {"suitNature": "830 Patent"},
                {"suitNature": ""},
                {"suitNature"},
            ),
            ["suitNature"],
        )

    def test_skips_fields_that_arent_comparable(self) -> None:
        """Are fields outside the comparable set left alone?"""
        self.assertEqual(
            get_out_of_sync_fields(
                {"dateFiled": "2026-07-15"}, {"dateFiled": None}, set()
            ),
            [],
        )

    def test_skips_keyword_fields_holding_non_text(self) -> None:
        """Is a keyword field holding an ID left alone?"""
        self.assertEqual(
            get_out_of_sync_fields(
                {"assigned_to_id": 42},
                {"assigned_to_id": 42},
                {"assigned_to_id"},
            ),
            [],
        )


class ComparableFieldsTest(SimpleTestCase):
    """Tests for picking the child fields worth comparing to their parent."""

    def setUp(self) -> None:
        self.config = get_sync_config(SEARCH_TYPES.RECAP)
        self.comparable_fields = get_comparable_fields(
            self.config.child_doc_class,
            ["suitNature", "cause", "dateFiled", "timestamp", "no_such_field"],
        )

    def test_includes_text_fields(self) -> None:
        """Are text fields comparable?"""
        self.assertEqual(self.comparable_fields, {"suitNature", "cause"})

    def test_excludes_dates(self) -> None:
        """Are dates excluded?

        They're serialized into `_source` differently from how they're held on
        the model, so an empty parent field would look like drift against a
        child's date string.
        """
        self.assertNotIn("dateFiled", self.comparable_fields)

    def test_excludes_the_timestamp_field(self) -> None:
        """Is timestamp excluded, given it records writes rather than content?"""
        self.assertNotIn("timestamp", self.comparable_fields)

    def test_excludes_unmapped_fields(self) -> None:
        """Is a name the child doesn't map excluded rather than raising?"""
        self.assertNotIn("no_such_field", self.comparable_fields)


class SyncConfigTest(SimpleTestCase):
    """Tests that the command syncs the fields the save signals maintain."""

    def test_recap_config_targets_recap_document_children(self) -> None:
        """Does the RECAP config describe the docket/RECAPDocument join?"""
        config = get_sync_config(SEARCH_TYPES.RECAP)
        self.assertEqual(config.child_doc_class.__name__, "ESRECAPDocument")
        self.assertEqual(config.child_join_type, "recap_document")
        self.assertIn("nature_of_suit", config.fields_to_update)

    def test_opinion_config_targets_opinion_children(self) -> None:
        """Does the opinion config describe the cluster/Opinion join?"""
        config = get_sync_config(SEARCH_TYPES.OPINION)
        self.assertEqual(config.child_doc_class.__name__, "OpinionDocument")
        self.assertEqual(config.child_join_type, "opinion")
        self.assertIn("case_name", config.fields_to_update)


class HandleIncompleteUbqUpdateTest(SimpleTestCase):
    """Tests for retrying an UpdateByQuery that didn't reach every child."""

    def assert_retried(self, task, response, expected_doc_count) -> None:
        """Assert the task scheduled a retry for the given response.

        :param task: The stand-in celery task.
        :param response: The stand-in UpdateByQuery response.
        :param expected_doc_count: The number of children the DB holds.
        :return: None
        """
        with self.assertRaises(Retry):
            handle_incomplete_ubq_update(
                task, response, expected_doc_count, "ESRECAPDocument", 1
            )
        task.retry.assert_called_once()

    def test_no_retry_when_every_child_was_updated(self) -> None:
        """Is a complete pass left alone?"""
        task = make_task()
        handle_incomplete_ubq_update(
            task, make_ubq_response(total=10), 10, "ESRECAPDocument", 1
        )
        task.retry.assert_not_called()

    def test_retries_when_children_were_not_matched(self) -> None:
        """Is a pass that missed children retried?

        This is the race that leaves children stale: an UpdateByQuery only
        touches documents that are already searchable.
        """
        task = make_task()
        self.assert_retried(task, make_ubq_response(total=8), 10)

    def test_retries_on_version_conflicts(self) -> None:
        """Is a pass that skipped contended documents retried?"""
        task = make_task()
        self.assert_retried(
            task, make_ubq_response(total=10, version_conflicts=2), 10
        )

    def test_retries_on_failures(self) -> None:
        """Is a pass that reported failures retried?"""
        task = make_task()
        self.assert_retried(
            task, make_ubq_response(total=10, failures=[{"status": 409}]), 10
        )

    def test_no_retry_when_more_documents_matched_than_expected(self) -> None:
        """Is a surplus of indexed children left alone?

        Children can outlive their database rows; that isn't the gap this
        guards against.
        """
        task = make_task()
        handle_incomplete_ubq_update(
            task, make_ubq_response(total=12), 10, "ESRECAPDocument", 1
        )
        task.retry.assert_not_called()

    def test_gives_up_after_one_retry(self) -> None:
        """Does a persistent mismatch stop retrying instead of failing?

        A gap that outlives the retry means children aren't indexed at all, and
        failing the task doesn't repair those.
        """
        task = make_task(retries=1)
        handle_incomplete_ubq_update(
            task, make_ubq_response(total=8), 10, "ESRECAPDocument", 1
        )
        task.retry.assert_not_called()
