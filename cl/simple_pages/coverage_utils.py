from typing import Any

from django.db.models import Max, Min

from cl.lib.elasticsearch_utils import get_opinions_coverage_chart_data
from cl.search.documents import OpinionClusterDocument
from cl.search.models import SOURCES, Court, Docket, OpinionCluster


async def fetch_data(jurisdictions, group_by_state=True):
    """Fetch Court Data

    Fetch data and organize it to group courts

    :param jurisdictions: The jurisdiction to query for
    :param group_by_state: Do we group by states
    :return: Ordered court data
    """
    courts = {}
    async for court in Court.objects.filter(
        jurisdiction__in=jurisdictions,
        parent_court__isnull=True,
    ).exclude(appeals_to__id="cafc"):
        court_has_content = await Docket.objects.filter(court=court).aexists()
        descendant_json = await get_descendants_dict(court)
        # Dont add any courts without a docket associated with it or
        # a descendant court
        if not court_has_content and not descendant_json:
            continue
        if group_by_state:
            courthouse = await court.courthouses.afirst()
            state = courthouse.get_state_display()
        else:
            state = "NONE"
        courts.setdefault(state, []).append(
            {
                "court": court,
                "descendants": descendant_json,
            }
        )
    return courts


async def get_descendants_dict(court):
    """Get descendants (if any) of court

    A simple method to help recsuively iterate for child courts

    :param court: Court object
    :return: Descendant courts
    """
    descendants = []
    async for child_court in court.child_courts.all():
        child_descendants = await get_descendants_dict(child_court)
        court_has_content = Docket.objects.filter(court=child_court).aexists()
        if court_has_content or child_descendants:
            descendants.append(
                {"court": child_court, "descendants": child_descendants}
            )
    return descendants


async def fetch_federal_data():
    """Gather federal court data hierarchically by circuits

    :return: A dict with the data in it
    """
    court_data = {}
    async for court in Court.objects.filter(
        jurisdiction=Court.FEDERAL_APPELLATE, parent_court__isnull=True
    ):
        court_data[court.id] = {
            "name": court.short_name,
            "id": court.id,
            "full_name": court.full_name,
        }
        if court.id == "scotus":
            continue
        elif court.id == "cafc":
            # Add Special Article I and III tribunals
            # that appeal cleanly to Federal Circuit
            accepts_appeals_from = {}
            async for appealing_court in court.appeals_from.all():
                accepts_appeals_from[appealing_court.id] = appealing_court
            court_data[court.id]["appeals_from"] = accepts_appeals_from
        else:
            filter_pairs = {
                "district": {
                    "jurisdiction": Court.FEDERAL_DISTRICT,
                },
                "bankruptcy": {
                    "jurisdiction__in": [
                        Court.FEDERAL_BANKRUPTCY,
                        Court.FEDERAL_BANKRUPTCY_PANEL,
                    ]
                },
                # Old circuit courts
                "circuit": {"parent_court__id": "uscirct"},
            }
            states_in_circuit = [
                courthouse["state"]
                async for courthouse in court.courthouses.values("state")
            ]
            # Add district court for canal zone
            if court.id == "ca5":
                states_in_circuit.extend(["CZ"])
            for label, filters in filter_pairs.items():
                # Get all the other courts in the geographic area of the
                # circuit court
                court_data[court.id][label] = Court.objects.filter(
                    courthouses__state__in=states_in_circuit,
                    **filters,
                ).distinct()
    return court_data


def build_chart_data(court_ids: list[str]):
    """Find and Organize Chart Data

    :param court_ids: List of court ids to chart
    :return: Chart data
    """
    grouped_data: dict[str, Any] = {}
    group_dict = dict(Court.JURISDICTIONS)

    chart_data_buckets = get_opinions_coverage_chart_data(
        OpinionClusterDocument.search(), court_ids
    )
    for bucket in chart_data_buckets:
        court_id = bucket.key
        if court_id not in court_ids:
            continue

        court = Court.objects.get(id=court_id)
        group = group_dict[court.jurisdiction]
        court_data_temp = {
            "id": court_id,
            "label": court.full_name,
        }
        court_data = court_data_temp.copy()
        court_data["data"] = [
            {
                "val": bucket.doc_count,
                "id": court_id,
                "timeRange": [
                    bucket.date_range.min_as_string,
                    bucket.date_range.max_as_string,
                ],
            }
        ]
        grouped_data.setdefault(group, []).append(court_data)  # type: ignore

        if court.has_opinion_scraper:
            # Query db for scraper data
            scraper_dates = OpinionCluster.objects.filter(
                docket__court=court_id,
                source__contains=SOURCES.COURT_WEBSITE,
            ).aggregate(
                earliest=Min("date_filed"),
                latest=Max("date_filed"),
            )
            if scraper_dates["earliest"]:
                scraper_data = court_data_temp.copy()
                scraper_data["data"] = [
                    {
                        "timeRange": list(scraper_dates.values()),
                        "id": court_id,
                    }
                ]
                grouped_data.setdefault("Scrapers", []).append(
                    scraper_data
                )  # type: ignore
    return [
        {"group": key, "data": value} for key, value in grouped_data.items()
    ]
