import datetime
import unittest
from functools import wraps

from django.utils import timezone

from cl.lib.utils import deepgetattr
from cl.search.constants import o_type_index_map
from cl.search.docket_sources import DocketSources
from cl.search.documents import DocketDocument
from cl.search.models import (
    Citation,
    Docket,
)


def midnight_pt_test(d: datetime.date) -> datetime.datetime:
    """Cast a naive date object to midnight Pacific Time, either PST or PDT,
    according to the date. This method also considers historical timezone
    offsets, similar to how they are handled in DRF.
    """
    time_zone = timezone.get_current_timezone()
    d = datetime.datetime.combine(d, datetime.time())
    return timezone.make_aware(d, time_zone)


opinion_cluster_v3_v4_common_fields = {
    "absolute_url": lambda x: x["result"].cluster.get_absolute_url(),
    "attorney": lambda x: x["result"].cluster.attorneys,
    "caseName": lambda x: (
        x["caseName"] if x.get("caseName") else x["result"].cluster.case_name
    ),
    "citation": lambda x: (
        x["citation"]
        if x.get("citation")
        else [str(cite) for cite in x["result"].cluster.citations.all()]
    ),
    "citeCount": lambda x: x["result"].cluster.citation_count,
    "court": lambda x: x["result"].cluster.docket.court.full_name,
    "court_citation_string": lambda x: (
        x["court_citation_string"]
        if x.get("court_citation_string")
        else x["result"].cluster.docket.court.citation_string
    ),
    "court_id": lambda x: x["result"].cluster.docket.court_id,
    "cluster_id": lambda x: x["result"].cluster_id,
    "docketNumber": lambda x: (
        x["docketNumber"]
        if x.get("docketNumber")
        else x["result"].cluster.docket.docket_number
    ),
    "docket_id": lambda x: x["result"].cluster.docket_id,
    "judge": lambda x: x["result"].cluster.judges,
    "lexisCite": lambda x: (
        str(x["result"].cluster.citations.filter(type=Citation.LEXIS)[0])
        if x["result"].cluster.citations.filter(type=Citation.LEXIS)
        else ""
    ),
    "neutralCite": lambda x: (
        str(x["result"].cluster.citations.filter(type=Citation.NEUTRAL)[0])
        if x["result"].cluster.citations.filter(type=Citation.NEUTRAL)
        else ""
    ),
    "scdb_id": lambda x: x["result"].cluster.scdb_id,
    "sibling_ids": lambda x: list(
        x["result"].cluster.sub_opinions.all().values_list("id", flat=True)
    ),
    "status": lambda x: (
        x["result"].cluster.precedential_status
        if x.get("V4")
        else x["result"].cluster.get_precedential_status_display()
    ),
    "suitNature": lambda x: (
        x["suitNature"]
        if x.get("suitNature")
        else x["result"].cluster.nature_of_suit
    ),
    "panel_ids": lambda x: (
        list(x["result"].cluster.panel.all().values_list("id", flat=True))
        if x["result"].cluster.panel.all()
        else []
        if x.get("V4")
        else None
    ),
    "dateArgued": lambda x: (
        (
            x["result"].cluster.docket.date_argued.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].cluster.docket.date_argued
            ).isoformat()
        )
        if x["result"].cluster.docket.date_argued
        else None
    ),
    "dateFiled": lambda x: (
        (
            x["result"].cluster.date_filed.isoformat()
            if x.get("V4")
            else midnight_pt_test(x["result"].cluster.date_filed).isoformat()
        )
        if x["result"].cluster.date_filed
        else None
    ),
    "dateReargued": lambda x: (
        (
            x["result"].cluster.docket.date_reargued.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].cluster.docket.date_reargued
            ).isoformat()
        )
        if x["result"].cluster.docket.date_reargued
        else None
    ),
    "dateReargumentDenied": lambda x: (
        (
            x["result"].cluster.docket.date_reargument_denied.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].cluster.docket.date_reargument_denied
            ).isoformat()
        )
        if x["result"].cluster.docket.date_reargument_denied
        else None
    ),
}

opinion_document_v3_v4_common_fields = {
    "author_id": lambda x: x["result"].author_id,
    "cites": lambda x: (
        list(
            x["result"]
            .cited_opinions.all()
            .values_list("cited_opinion_id", flat=True)
        )
        if x["result"]
        .cited_opinions.all()
        .values_list("cited_opinion_id", flat=True)
        else []
        if x.get("V4")
        else None
    ),
    "download_url": lambda x: x["result"].download_url,
    "id": lambda x: x["result"].pk,
    "joined_by_ids": lambda x: (
        list(x["result"].joined_by.all().values_list("id", flat=True))
        if x["result"].joined_by.all()
        else []
        if x.get("V4")
        else None
    ),
    "type": lambda x: (
        o_type_index_map.get(x["result"].type)
        if x.get("V4")
        else x["result"].type
    ),
    "local_path": lambda x: (
        x["result"].local_path if x["result"].local_path else None
    ),
    "per_curiam": lambda x: x["result"].per_curiam,
    "snippet": lambda x: (
        x["snippet"] if x.get("snippet") else x["result"].plain_text or ""
    ),
    "ordering_key": lambda x: x["result"].ordering_key,
}

opinion_cluster_v3_fields = opinion_cluster_v3_v4_common_fields.copy()
opinion_document_v3_fields = opinion_document_v3_v4_common_fields.copy()

opinion_v3_search_api_keys = {
    "court_exact": lambda x: x["result"].cluster.docket.court_id,
    "date_created": lambda x: (
        x["result"].date_created.isoformat().replace("+00:00", "Z")
        if x.get("V4")
        else timezone.localtime(x["result"].cluster.date_created).isoformat()
    ),
    "timestamp": lambda x: (
        x["result"].date_created.isoformat().replace("+00:00", "Z")
        if x.get("V4")
        else timezone.localtime(x["result"].cluster.date_created).isoformat()
    ),
}
opinion_v3_search_api_keys.update(opinion_cluster_v3_fields)
opinion_v3_search_api_keys.update(opinion_document_v3_fields)

opinion_v4_search_api_keys = {
    "non_participating_judge_ids": lambda x: (
        list(
            x["result"]
            .cluster.non_participating_judges.all()
            .values_list("id", flat=True)
        )
    ),
    "source": lambda x: x["result"].cluster.source,
    "caseNameFull": lambda x: x["result"].cluster.case_name_full,
    "panel_names": lambda x: [
        judge.name_full for judge in x["result"].cluster.panel.all()
    ],
    "procedural_history": lambda x: x["result"].cluster.procedural_history,
    "posture": lambda x: x["result"].cluster.posture,
    "syllabus": lambda x: x["result"].cluster.syllabus,
    "opinions": [],  # type: ignore
    "meta": [],
}

opinion_cluster_v4_common_fields = opinion_cluster_v3_v4_common_fields.copy()
opinion_v4_search_api_keys.update(opinion_cluster_v4_common_fields)

opinion_document_v4_api_keys = {
    "sha1": lambda x: x["result"].sha1,
    "meta": [],
}
opinion_document_v4_api_keys.update(opinion_document_v3_v4_common_fields)

docket_api_common_keys = {
    "assignedTo": lambda x: (
        x["assignedTo"]
        if x.get("assignedTo")
        else (
            x["result"].docket_entry.docket.assigned_to.name_full
            if x["result"].docket_entry.docket.assigned_to
            else None
        )
    ),
    "assigned_to_id": lambda x: (
        x["result"].docket_entry.docket.assigned_to.pk
        if x["result"].docket_entry.docket.assigned_to
        else None
    ),
    "caseName": lambda x: (
        x["caseName"]
        if x.get("caseName")
        else x["result"].docket_entry.docket.case_name
    ),
    "cause": lambda x: (
        x["cause"] if x.get("cause") else x["result"].docket_entry.docket.cause
    ),
    "court": lambda x: x["result"].docket_entry.docket.court.full_name,
    "court_citation_string": lambda x: (
        x["court_citation_string"]
        if x.get("court_citation_string")
        else x["result"].docket_entry.docket.court.citation_string
    ),
    "court_id": lambda x: x["result"].docket_entry.docket.court.pk,
    "dateArgued": lambda x: (
        (
            x["result"].docket_entry.docket.date_argued.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].docket_entry.docket.date_argued
            ).isoformat()
        )
        if x["result"].docket_entry.docket.date_argued
        else None
    ),
    "dateFiled": lambda x: (
        (
            x["result"].docket_entry.docket.date_filed.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].docket_entry.docket.date_filed
            ).isoformat()
        )
        if x["result"].docket_entry.docket.date_filed
        else None
    ),
    "dateTerminated": lambda x: (
        (
            x["result"].docket_entry.docket.date_terminated.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].docket_entry.docket.date_terminated
            ).isoformat()
        )
        if x["result"].docket_entry.docket.date_terminated
        else None
    ),
    "docketNumber": lambda x: (
        x["docketNumber"]
        if x.get("docketNumber")
        else x["result"].docket_entry.docket.docket_number
    ),
    "docket_id": lambda x: x["result"].docket_entry.docket_id,
    "jurisdictionType": lambda x: x[
        "result"
    ].docket_entry.docket.jurisdiction_type,
    "juryDemand": lambda x: (
        x["juryDemand"]
        if x.get("juryDemand")
        else x["result"].docket_entry.docket.jury_demand
    ),
    "referredTo": lambda x: (
        x["referredTo"]
        if x.get("referredTo")
        else (
            x["result"].docket_entry.docket.referred_to.name_full
            if x["result"].docket_entry.docket.referred_to
            else None
        )
    ),
    "referred_to_id": lambda x: (
        x["result"].docket_entry.docket.referred_to.pk
        if x["result"].docket_entry.docket.referred_to
        else None
    ),
    "suitNature": lambda x: (
        x["suitNature"]
        if x.get("suitNature")
        else x["result"].docket_entry.docket.nature_of_suit
    ),
}

recap_type_v4_api_keys = docket_api_common_keys.copy()
recap_type_v4_api_keys.update(
    {
        "attorney": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "attorney"
            ]
        ),
        "attorney_id": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "attorney_id"
            ]
        ),
        "case_name_full": lambda x: x[
            "result"
        ].docket_entry.docket.case_name_full,
        "chapter": lambda x: (
            x["result"].docket_entry.docket.bankruptcy_information.chapter
            if hasattr(
                x["result"].docket_entry.docket, "bankruptcy_information"
            )
            else None
        ),
        "docket_absolute_url": lambda x: x[
            "result"
        ].docket_entry.docket.get_absolute_url(),
        "firm": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "firm"
            ]
        ),
        "firm_id": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "firm_id"
            ]
        ),
        "pacer_case_id": lambda x: (
            str(x["result"].docket_entry.docket.pacer_case_id)
            if x["result"].docket_entry.docket.pacer_case_id
            else ""
        ),
        "party": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "party"
            ]
        ),
        "party_id": lambda x: list(
            DocketDocument().prepare_parties(x["result"].docket_entry.docket)[
                "party_id"
            ]
        ),
        "trustee_str": lambda x: (
            x["result"].docket_entry.docket.bankruptcy_information.trustee_str
            if hasattr(
                x["result"].docket_entry.docket, "bankruptcy_information"
            )
            else None
        ),
        "meta": [],  # type: ignore
        "recap_documents": [],  # type: ignore
    }
)

recap_document_common_api_keys = {
    "id": lambda x: x["result"].pk,
    "docket_entry_id": lambda x: x["result"].docket_entry.pk,
    "description": lambda x: (
        x["description"]
        if x.get("description")
        else x["result"].docket_entry.description
    ),
    "entry_number": lambda x: x["result"].docket_entry.entry_number,
    "entry_date_filed": lambda x: (
        (
            x["result"].docket_entry.date_filed.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].docket_entry.date_filed
            ).isoformat()
        )
        if x["result"].docket_entry.date_filed
        else None
    ),
    "short_description": lambda x: (
        x["short_description"]
        if x.get("short_description")
        else x["result"].description
    ),
    "document_type": lambda x: x["result"].get_document_type_display(),
    "document_number": lambda x: (
        int(x["result"].document_number)
        if x["result"].document_number
        else None
    ),
    "snippet": lambda x: (
        x["snippet"] if x.get("snippet") else x["result"].plain_text or ""
    ),
    "attachment_number": lambda x: x["result"].attachment_number or None,
    "is_available": lambda x: x["result"].is_available,
    "page_count": lambda x: x["result"].page_count or None,
    "filepath_local": lambda x: x["result"].filepath_local.name or None,
    "absolute_url": lambda x: x["result"].get_absolute_url(),
}

recap_document_v4_api_keys = recap_document_common_api_keys.copy()
recap_document_v4_api_keys.update(
    {
        "pacer_doc_id": lambda x: x["result"].pacer_doc_id or "",
        "cites": lambda x: list(
            x["result"]
            .cited_opinions.all()
            .values_list("cited_opinion_id", flat=True)
        ),
        "meta": [],  # type: ignore
    }
)

rd_type_v4_api_keys = recap_document_v4_api_keys.copy()
rd_type_v4_api_keys.update(
    {
        "docket_id": lambda x: x["result"].docket_entry.docket_id,
    }
)

v4_meta_keys = {
    "date_created": lambda x: x["result"]
    .date_created.isoformat()
    .replace("+00:00", "Z"),
    "timestamp": lambda x: x["result"]
    .date_created.isoformat()
    .replace("+00:00", "Z"),
    "score": lambda x: {"bm25": None},
}

v4_recap_meta_keys = v4_meta_keys.copy()
v4_recap_meta_keys.update(
    {
        "more_docs": lambda x: False,
    }
)

recap_v3_keys = docket_api_common_keys.copy()

recap_v3_keys.update(recap_document_common_api_keys)
recap_v3_keys.update(
    {
        "court_exact": lambda x: x["result"].docket_entry.docket.court.pk,
        "timestamp": lambda x: timezone.localtime(
            x["result"].date_created
        ).isoformat(),
    }
)


people_v4_fields = {
    "absolute_url": lambda x: x["result"].person.get_absolute_url(),
    "date_granularity_dob": lambda x: x["result"].person.date_granularity_dob,
    "date_granularity_dod": lambda x: x["result"].person.date_granularity_dod,
    "id": lambda x: x["result"].person.pk,
    "alias_ids": lambda x: (
        [alias.pk for alias in x["result"].person.aliases.all()]
        if x["result"].person.aliases.all()
        else []
    ),
    "races": lambda x: (
        [r.get_race_display() for r in x["result"].person.race.all()]
        if x["result"].person.race.all()
        else []
    ),
    "political_affiliation_id": lambda x: (
        [
            pa.political_party
            for pa in x["result"].person.political_affiliations.all()
        ]
        if x["result"].person.political_affiliations.all()
        else []
    ),
    "fjc_id": lambda x: str(x["result"].person.fjc_id),
    "name": lambda x: (
        x["name"] if x.get("name") else x["result"].person.name_full
    ),
    "gender": lambda x: x["result"].person.get_gender_display(),
    "religion": lambda x: x["result"].person.religion,
    "alias": lambda x: (
        [r.name_full for r in x["result"].person.aliases.all()]
        if x["result"].person.aliases.all()
        else []
    ),
    "dob": lambda x: (
        x["result"].person.date_dob.isoformat()
        if x["result"].person.date_dob
        else None
    ),
    "dod": lambda x: (
        x["result"].person.date_dod.isoformat()
        if x["result"].person.date_dod
        else None
    ),
    "dob_city": lambda x: (
        x["dob_city"] if x.get("dob_city") else x["result"].person.dob_city
    ),
    "dob_state": lambda x: x["result"].person.get_dob_state_display(),
    "dob_state_id": lambda x: (
        x["dob_state_id"]
        if x.get("dob_state_id")
        else x["result"].person.dob_state
    ),
    "political_affiliation": lambda x: (
        x["political_affiliation"]
        if x.get("political_affiliation")
        else (
            [
                pa.get_political_party_display()
                for pa in x["result"].person.political_affiliations.all()
            ]
            if x["result"].person.political_affiliations.all()
            else []
        )
    ),
    "positions": [],  # type: ignore
    "aba_rating": lambda x: (
        [r.get_rating_display() for r in x["result"].person.aba_ratings.all()]
        if x["result"].person.aba_ratings.all()
        else []
    ),
    "school": lambda x: (
        x["school"]
        if x.get("school")
        else (
            [e.school.name for e in x["result"].person.educations.all()]
            if x["result"].person.educations.all()
            else []
        )
    ),
    "meta": [],
}

position_v4_fields = {
    "court": lambda x: (
        x["result"].court.short_name if x["result"].court else None
    ),
    "court_full_name": lambda x: (
        x["result"].court.full_name if x["result"].court else None
    ),
    "court_exact": lambda x: (
        x["result"].court.pk if x["result"].court else None
    ),
    "court_citation_string": lambda x: (
        x["result"].court.citation_string if x["result"].court else None
    ),
    "organization_name": lambda x: x["result"].organization_name,
    "job_title": lambda x: x["result"].job_title,
    "position_type": lambda x: x["result"].get_position_type_display(),
    "appointer": lambda x: (
        x["result"].appointer.person.name_full_reverse
        if x["result"].appointer and x["result"].appointer.person
        else None
    ),
    "supervisor": lambda x: (
        x["result"].supervisor.name_full_reverse
        if x["result"].supervisor
        else None
    ),
    "predecessor": lambda x: (
        x["result"].predecessor.name_full_reverse
        if x["result"].predecessor
        else None
    ),
    "date_nominated": lambda x: (
        x["result"].date_nominated.isoformat()
        if x["result"].date_nominated
        else None
    ),
    "date_elected": lambda x: (
        x["result"].date_elected.isoformat()
        if x["result"].date_elected
        else None
    ),
    "date_recess_appointment": lambda x: (
        x["result"].date_recess_appointment.isoformat()
        if x["result"].date_recess_appointment
        else None
    ),
    "date_referred_to_judicial_committee": lambda x: (
        x["result"].date_referred_to_judicial_committee.isoformat()
        if x["result"].date_referred_to_judicial_committee
        else None
    ),
    "date_judicial_committee_action": lambda x: (
        x["result"].date_judicial_committee_action.isoformat()
        if x["result"].date_judicial_committee_action
        else None
    ),
    "date_hearing": lambda x: (
        x["result"].date_hearing.isoformat()
        if x["result"].date_hearing
        else None
    ),
    "date_confirmation": lambda x: (
        x["result"].date_confirmation.isoformat()
        if x["result"].date_confirmation
        else None
    ),
    "date_start": lambda x: (
        x["result"].date_start.isoformat() if x["result"].date_start else None
    ),
    "date_granularity_start": lambda x: x["result"].date_granularity_start,
    "date_retirement": lambda x: (
        x["result"].date_retirement.isoformat()
        if x["result"].date_retirement
        else None
    ),
    "date_termination": lambda x: (
        x["result"].date_termination.isoformat()
        if x["result"].date_termination
        else None
    ),
    "date_granularity_termination": lambda x: x[
        "result"
    ].date_granularity_termination,
    "judicial_committee_action": lambda x: x[
        "result"
    ].get_judicial_committee_action_display(),
    "nomination_process": lambda x: x[
        "result"
    ].get_nomination_process_display(),
    "selection_method": lambda x: x["result"].get_how_selected_display(),
    "selection_method_id": lambda x: x["result"].how_selected,
    "termination_reason": lambda x: x[
        "result"
    ].get_termination_reason_display(),
    "meta": [],
}

audio_common_fields = {
    "absolute_url": lambda x: x["result"].get_absolute_url(),
    "caseName": lambda x: (
        x["caseName"] if x.get("caseName") else x["result"].case_name
    ),
    "court": lambda x: x["result"].docket.court.full_name,
    "court_id": lambda x: x["result"].docket.court.pk,
    "court_citation_string": lambda x: (
        x["court_citation_string"]
        if x.get("court_citation_string")
        else x["result"].docket.court.citation_string
    ),
    "docket_id": lambda x: x["result"].docket.pk,
    "dateArgued": lambda x: (
        (
            x["result"].docket.date_argued.isoformat()
            if x.get("V4")
            else midnight_pt_test(x["result"].docket.date_argued).isoformat()
        )
        if x["result"].docket.date_argued
        else None
    ),
    "dateReargued": lambda x: (
        (
            x["result"].docket.date_reargued.isoformat()
            if x.get("V4")
            else midnight_pt_test(x["result"].docket.date_reargued).isoformat()
        )
        if x["result"].docket.date_reargued
        else None
    ),
    "dateReargumentDenied": lambda x: (
        (
            x["result"].docket.date_reargument_denied.isoformat()
            if x.get("V4")
            else midnight_pt_test(
                x["result"].docket.date_reargument_denied
            ).isoformat()
        )
        if x["result"].docket.date_reargument_denied
        else None
    ),
    "docketNumber": lambda x: (
        x["docketNumber"]
        if x.get("docketNumber")
        else x["result"].docket.docket_number
    ),
    "duration": lambda x: x["result"].duration,
    "download_url": lambda x: x["result"].download_url,
    "file_size_mp3": lambda x: (
        deepgetattr(x["result"], "local_path_mp3.size", None)
        if x["result"].local_path_mp3
        else None
    ),
    "id": lambda x: x["result"].pk,
    "judge": lambda x: (
        x["judge"]
        if x.get("judge")
        else x["result"].judges
        if x["result"].judges
        else ""
    ),
    "local_path": lambda x: (
        deepgetattr(x["result"], "local_path_mp3.name", None)
        if x["result"].local_path_mp3
        else None
    ),
    "pacer_case_id": lambda x: x["result"].docket.pacer_case_id,
    "panel_ids": lambda x: (
        list(x["result"].panel.all().values_list("id", flat=True))
        if x["result"].panel.all()
        else []
        if x.get("V4")
        else None
    ),
    "sha1": lambda x: x["result"].sha1,
    "source": lambda x: x["result"].source,
    "snippet": lambda x: (
        x["snippet"]
        if x.get("snippet")
        else x["result"].transcript
        if x["result"].stt_transcript
        else ""
    ),
}


audio_v3_fields = audio_common_fields.copy()
audio_v3_fields.update(
    {
        "court_exact": lambda x: x["result"].docket.court.pk,
        "date_created": lambda x: timezone.localtime(
            x["result"].date_created
        ).isoformat(),
        "timestamp": lambda x: timezone.localtime(
            x["result"].date_created
        ).isoformat(),
    }
)


audio_v4_fields = audio_common_fields.copy()
audio_v4_fields.update(
    {
        "case_name_full": lambda x: x["result"].case_name_full,
        "meta": [],  # type: ignore
    }
)


def skip_if_common_tests_skipped(method):
    """Decorator to skip common tests based on the skip_common_tests attribute."""

    @wraps(method)
    async def wrapper_func(self, *args, **kwargs):
        if getattr(self, "skip_common_tests", False):
            raise unittest.SkipTest("Skip common tests within the class.")
        return await method(self, *args, **kwargs)

    return wrapper_func


def generate_docket_target_sources(
    initial_sources: list[int], incoming_source: int
) -> dict[str, str]:
    """Generates a mapping for testing of docket target sources based on
    initial sources and an incoming source.

    :param initial_sources: A list of integers representing the initial source
     values.
    :param incoming_source: An integer representing the incoming source value
    to be added to each of the initial sources.
    :return: A dict mapping from initial source names to target source names,
    based on the sum of the initial source value and the incoming source value.
    e.g: {"RECAP": "COLUMBIA_AND_RECAP"}
    """
    inverse_sources = {
        value: key
        for key, value in DocketSources.__dict__.items()
        if not key.startswith("__") and isinstance(value, int)
    }

    target_sources = {}
    for source in initial_sources:
        target_source = source + incoming_source
        if incoming_source == Docket.RECAP and source == Docket.DEFAULT:
            # Exception for  DEFAULT + RECAP source assignation.
            target_sources[inverse_sources[source]] = "RECAP_AND_SCRAPER"
        else:
            target_sources[inverse_sources[source]] = inverse_sources[
                target_source
            ]

    return target_sources
