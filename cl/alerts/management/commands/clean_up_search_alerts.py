import argparse
import time
from typing import Callable, cast

from django.http import QueryDict
from elasticsearch.exceptions import ApiError, RequestError

from cl.alerts.models import Alert
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.elasticsearch_utils import build_es_base_query
from cl.lib.types import OptionsType
from cl.search.documents import OpinionClusterDocument
from cl.search.exception import (
    BadProximityQuery,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm
from cl.search.models import PRECEDENTIAL_STATUS, SEARCH_TYPES


def clean_up_alerts(options: OptionsType) -> None:
    """Clean up Opinions search alert queries to reflect the new
     Precedential status values in ES.

    :return: None
    """
    filter_replacements = {
        "stat_Precedential": f"stat_{PRECEDENTIAL_STATUS.PUBLISHED}",
        "stat_Non-Precedential": f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}",
        "stat_Errata": f"stat_{PRECEDENTIAL_STATUS.ERRATA}",
        "stat_Separate%20Opinion": f"stat_{PRECEDENTIAL_STATUS.SEPARATE}",
        "stat_In-chambers": f"stat_{PRECEDENTIAL_STATUS.IN_CHAMBERS}",
        "stat_Relating-to%20orders": f"stat_{PRECEDENTIAL_STATUS.RELATING_TO}",
        "stat_Unknown%20Status": f"stat_{PRECEDENTIAL_STATUS.UNKNOWN}",
    }
    alerts = Alert.objects.filter(alert_type=SEARCH_TYPES.OPINION).only(
        "query"
    )
    replacement_count = 0
    for alert in alerts.iterator():
        alert_query_original = alert.query
        alert_query = alert.query
        for old_filter, new_filter in filter_replacements.items():
            alert_query = alert_query.replace(old_filter, new_filter)

        if alert_query != alert_query_original:
            # Only update the alert if it's changed.
            alert.query = alert_query
            alert.save()
            replacement_count += 1

    logger.info(
        f"\r Successfully fixed {replacement_count} opinions search alerts."
    )


def validate_queries_syntax(options: OptionsType) -> None:
    """Validate the syntax of query strings in opinion search alerts.

    The objetive of this validation is to identify and log any opinion search
    alerts with query strings that could lead to syntax issues.

    :return: None
    """
    waiting_time = cast(int, options["validation_wait"])
    alerts = Alert.objects.filter(alert_type=SEARCH_TYPES.OPINION).only(
        "pk", "query"
    )

    search_query = OpinionClusterDocument.search()
    queries_count = 0
    invalid_queries = 0
    for alert in alerts.iterator():
        qd = QueryDict(alert.query.encode(), mutable=True)
        search_form = SearchForm(qd)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            try:
                s, _ = build_es_base_query(search_query, cd)
                s = s.extra(size=0)
                s.execute().to_dict()
                # Waiting between requests to avoid hammering ES too quickly.
                time.sleep(waiting_time)
            except (
                RequestError,
                UnbalancedParenthesesQuery,
                UnbalancedQuotesQuery,
                BadProximityQuery,
                ApiError,
            ) as e:
                logger.error(
                    "Invalid Search Alert syntax. ID: %s, error: %s",
                    alert.pk,
                    e,
                )
                invalid_queries += 1

        queries_count += 1
    logger.info(
        f"\r Checked {queries_count} opinions search alerts. There were {invalid_queries} invalid queries."
    )


class Command(VerboseCommand):
    help = "Clean up Opinion Search alerts and validate their query syntax."

    def valid_actions(self, s: str) -> Callable:
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )
        parser.add_argument(
            "--validation-wait",
            type=int,
            default="1",
            help="The time to wait between ES query validation checks.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if isinstance(options["action"], str):
            action_function = self.VALID_ACTIONS[options["action"]]
        else:
            action_function = options["action"]
        action = cast(Callable, action_function)
        action(options)

    VALID_ACTIONS = {
        "clean-up": clean_up_alerts,
        "validate-queries": validate_queries_syntax,
    }
