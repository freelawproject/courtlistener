from typing import Dict, Tuple, Union

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib.string_utils import trunc
from cl.recap.constants import COURT_TIMEZONES
from cl.search.models import Docket, OpinionCluster


def get_case_title(cluster: OpinionCluster) -> str:
    return f"{trunc(best_case_name(cluster), 100)}, {cluster.citation_string}"


def make_docket_title(docket: Docket) -> str:
    title = ", ".join(
        [
            s
            for s in [
                trunc(best_case_name(docket), 100, ellipsis="..."),
                docket.docket_number,
            ]
            if s and s.strip()
        ]
    )
    return title


def core_docket_data(
    request: HttpRequest,
    pk: int,
) -> Tuple[Docket, Dict[str, Union[bool, str, Docket, NoteForm]]]:
    """Gather the core data for a docket, party, or IDB page."""
    docket = get_object_or_404(Docket, pk=pk)
    title = make_docket_title(docket)

    try:
        note = Note.objects.get(docket_id=docket.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not saved in notes or anonymous user
        note_form = NoteForm(
            initial={
                "docket_id": docket.pk,
                "name": trunc(best_case_name(docket), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    has_alert = user_has_alert(request.user, docket)

    return (
        docket,
        {
            "docket": docket,
            "title": title,
            "note_form": note_form,
            "has_alert": has_alert,
            "timezone": COURT_TIMEZONES.get(docket.court_id, "US/Eastern"),
            "private": docket.blocked,
        },
    )


def user_has_alert(user: Union[AnonymousUser, User], docket: Docket) -> bool:
    has_alert = False
    if user.is_authenticated:
        has_alert = DocketAlert.objects.filter(
            docket=docket, user=user, alert_type=DocketAlert.SUBSCRIPTION
        ).exists()
    return has_alert
