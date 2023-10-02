from cl.search.models import Court, Docket


def fetch_data(jurisdictions, group_by_state=True):
    """Fetch Court Data

    Fetch data and organize it to group courts

    :param jurisdictions: The jurisdiction to query for
    :param group_by_state: Do we group by states
    :return: Ordered court data
    """
    courts = {}
    for court in Court.objects.filter(
        jurisdiction__in=jurisdictions,
        parent_court__isnull=True,
    ).exclude(appeals_to__id="cafc"):
        court_has_content = Docket.objects.filter(court=court).exists()
        descendant_json = get_descendants_dict(court)
        # Dont add any courts without a docket associated with it or
        # a descendant court
        if not court_has_content and not descendant_json:
            continue
        if group_by_state:
            state = court.courthouses.first().get_state_display()
        else:
            state = "NONE"
        courts.setdefault(state, []).append(
            {
                "court": court,
                "descendants": descendant_json,
            }
        )
    return courts


def get_descendants_dict(court):
    """Get descendants (if any) of court

    A simple method to help recsuively iterate for child courts

    :param court: Court object
    :return: Descendant courts
    """
    descendants = []
    for child_court in court.child_courts.all():
        child_descendants = get_descendants_dict(child_court)
        court_has_content = Docket.objects.filter(court=child_court).exists()
        if court_has_content or child_descendants:
            descendants.append(
                {"court": child_court, "descendants": child_descendants}
            )
    return descendants


def fetch_federal_data():
    """Gather federal court data hierarchically by circuits

    :return: A dict with the data in it
    """
    court_data = {}
    for court in Court.objects.filter(
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
            for appealing_court in court.appeals_from.all():
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
                for courthouse in court.courthouses.values("state")
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
