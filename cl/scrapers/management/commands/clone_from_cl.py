"""
This tool allows you to partially clone data from courtlistener.com to your
local environment, you only need to pass the type and object id and run it.

manage.py clone_from_cl --type search.OpinionCluster --id 9355884
manage.py clone_from_cl --type search.Docket --id 5377675
manage.py clone_from_cl --type people_db.Person --id 16207
manage.py clone_from_cl --type search.Court --id usnmcmilrev
manage.py clone_from_cl --type audio.Audio --id 101435

This tool is only for development purposes, so it only works when
the DEVELOPMENT env is set to True. It also relies on the CL_API_TOKEN
env variable.

You can also pass the api token before running the command:

CL_API_TOKEN='my_api_key' manage.py clone_from_cl --type search.OpinionCluster --id 9355884

You can also clone multiple objects at the same time, for example:

manage.py clone_from_cl --type search.OpinionCluster --id 1867834 1867833
manage.py clone_from_cl --type search.Docket --id 14614371 5377675
manage.py clone_from_cl --type search.Court --id mspb leechojibtr
manage.py clone_from_cl --type people_db.Person --id 16212 16211

Now you can clone docket entries and recap documents if you have the
permissions. If the Docket already exists, the entries and documents will be
updated. For example:

manage.py clone_from_cl --type search.Docket --id 17090923 --add-docket-entries

You can also clone audio files (oral arguments) related to a docket. For example:

manage.py clone_from_cl --type search.Docket --id 66635300 18473600 --add-audio-files

Now you can clone people positions, for example:

manage.py clone_from_cl --type search.OpinionCluster --id 1814616 --clone-person-positions
manage.py clone_from_cl --type people_db.Person --id 4173 --clone-person-positions
manage.py clone_from_cl --type search.Docket --id 5377675 --clone-person-positions

To clone opinions with its local_path file you need to set the AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
AWS_SESSION_TOKEN so the files can be saved. To do it run it like this:

docker exec -it cl-django python /opt/courtlistener/manage.py clone_from_cl --type search.OpinionCluster --download-opinion-files --id 4833422

To clone audio files directly:

docker exec -it cl-django python /opt/courtlistener/manage.py clone_from_cl --type audio.Audio --id 101435

If you don't want the objects to be updated, add the --no-update parameter to any of the above commands.

Note: for cloned Opinion Clusters to appear in docket authorities pages, use the
`find_citations_and_parantheticals_for_recap_documents` method in the Django shell.
You can pass all RECAPDocument IDs, for example:
`RECAPDocument.objects.values_list('pk', flat=True)`, or only a subset if needed.

This is still work in progress, some data is not cloned yet.
"""

import json
import os
import pathlib
import sys
from datetime import datetime

import requests
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import BaseCommand
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.dateparse import parse_date
from requests import Session

from cl.audio.models import Audio
from cl.people_db.models import Person, Position
from cl.search.models import (
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    RECAPDocument,
    Tag,
)

VALID_TYPES = (
    "search.OpinionCluster",
    "search.Docket",
    "people_db.Person",
    "search.Court",
    "audio.Audio",
)

DOMAIN = "https://www.courtlistener.com"

LOCAL_PATH_DOMAIN = "https://com-courtlistener-storage.s3.amazonaws.com"

PROD_STORAGE_PATH = "https://storage.courtlistener.com"


class CloneException(Exception):
    """Error found in clone process."""

    def __init__(self, message: str) -> None:
        self.message = message


def clean_api_data(data: dict, fields_to_remove: list[str] = None) -> dict:
    """Remove fields that shouldn't be saved to the db

    :param data: The dictionary data obtained from the CourtListener API.
    :param fields_to_remove: A list of specific keys to remove in addition to the defaults.
    :return: The cleaned dictionary ready for database insertion/update.
    """
    default_fields_to_remove = ["resource_uri", "absolute_url"]
    removals = default_fields_to_remove + (fields_to_remove or [])
    for field in removals:
        data.pop(field, None)
    return data


def get_id_from_url(api_url: str) -> str:
    """Get the PK from an API url

    :param api_url: api url with a pk
    :return: pk from url
    """
    return api_url.split("/")[-2]


def get_json_data(api_url: str, session: Session, timeout: int = 120) -> dict:
    """Get the JSON data from endpoint

    :param api_url: api url to send get request
    :param session: a Requests session
    :param timeout: timeout for get request
    :return: list of opinion cluster objects
    """
    data = session.get(api_url, timeout=timeout)

    if data.status_code == 401:
        print("Error: Invalid token in CL_API_TOKEN variable.")
        sys.exit(1)

    return data.json()


def clone_opinion_cluster(
    session: Session,
    cluster_ids: list,
    download_cluster_files: bool,
    add_docket_entries: bool,
    person_positions: bool = False,
    download_opinion_files: bool = False,
    no_update: bool = False,
):
    """Download opinion cluster data from courtlistener.com and add it to
    local environment

    :param session: a Requests session
    :param cluster_ids: a list of opinion cluster ids
    :param download_cluster_files: True if it should download cluster files
    :param add_docket_entries: flag to clone docket entries and recap docs
    :param person_positions: True if we should clone person positions
    :param download_opinion_files: True if we should download local_path file from opinion
    :param no_update: If True, skip updating object if it already exists
    :return: list of opinion cluster objects
    """

    opinion_clusters = []

    for cluster_id in cluster_ids:
        print(f"Cloning opinion cluster id: {cluster_id}")

        if no_update and OpinionCluster.objects.filter(pk=cluster_id).exists():
            op = OpinionCluster.objects.get(pk=cluster_id)
            print(
                "Opinion cluster already exists here:",
                reverse(
                    "view_case",
                    args=[op.pk, op.docket.slug],
                ),
            )
            opinion_clusters.append(op)
            continue

        cluster_path = reverse(
            "opinioncluster-detail",
            kwargs={"version": "v4", "pk": cluster_id},
        )
        cluster_url = f"{DOMAIN}{cluster_path}"
        cluster_data = get_json_data(cluster_url, session)
        docket_url = cluster_data.pop("docket")
        docket_id = get_id_from_url(docket_url)
        citation_data = cluster_data.pop("citations", [])
        panel_data = cluster_data.pop("panel", [])
        non_participating_judges_data = cluster_data.pop(
            "non_participating_judges", []
        )
        sub_opinions_urls = cluster_data.pop("sub_opinions", [])
        filepath_json_harvard = cluster_data.pop("filepath_json_harvard", None)

        # delete unneeded fields
        clean_api_data(cluster_data)

        # clone docket
        docket = clone_docket(
            session,
            [docket_id],
            add_docket_entries=add_docket_entries,
            add_audio_files=False,
            add_clusters=False,
            person_positions=person_positions,
        )[0]

        # Assign docket pk in cluster data
        cluster_data["docket_id"] = docket.pk

        # Clone panel data
        panel_ids = [get_id_from_url(p) for p in panel_data]
        if panel_ids:
            clone_person(session, panel_ids, person_positions, no_update)
        # Clone non participating judges data
        non_participating_judges_ids = [
            get_id_from_url(p) for p in non_participating_judges_data
        ]
        if non_participating_judges_ids:
            clone_person(
                session,
                non_participating_judges_ids,
                person_positions,
                no_update,
            )

        with transaction.atomic():
            # Create opinion cluster
            opinion_cluster, created = OpinionCluster.objects.update_or_create(
                id=cluster_data["id"], defaults=cluster_data
            )

            if download_cluster_files and filepath_json_harvard:
                try:
                    ia_url = cluster_data.get("filepath_json_harvard").replace(
                        "/storage/harvard_corpus/",
                        "https://archive.org/download/",
                    )

                    req = requests.get(
                        ia_url, allow_redirects=True, timeout=120
                    )

                    if req.status_code == 200:
                        print(f"Downloading {ia_url}")
                        json_harvard_content = json.dumps(req.json(), indent=4)
                        path = pathlib.PurePath(
                            cluster_data.get("filepath_json_harvard")
                        )
                        json_path = os.path.join(
                            "harvard_corpus", path.parent.name, path.name
                        )
                        opinion_cluster.filepath_json_harvard.save(
                            json_path, ContentFile(json_harvard_content)
                        )

                except Exception:
                    print(
                        "Can't download filepath_json_harvard file for "
                        f"cluster id: {cluster_id}"
                    )

            opinion_cluster.panel.set(Person.objects.filter(id__in=panel_ids))
            opinion_cluster.non_participating_judges.set(
                Person.objects.filter(id__in=non_participating_judges_ids)
            )

            opinion_cluster.citations.all().delete()
            for cite_data in citation_data:
                # Create citations
                cite_data["cluster_id"] = opinion_cluster.pk
                Citation.objects.create(**cite_data)

            # Clone opinions
            sub_opinions_ids = [
                get_id_from_url(url) for url in sub_opinions_urls
            ]
            for opinion_id in sub_opinions_ids:
                clone_opinion(
                    session,
                    int(opinion_id),
                    opinion_cluster.pk,
                    person_positions,
                    download_opinion_files,
                )

            opinion_clusters.append(opinion_cluster)
            action = "Created" if created else "Updated"
            print(
                f"({action}) View cloned case here: {reverse('view_case', args=[opinion_cluster.pk, docket.slug])}",
            )

    return opinion_clusters


def clone_opinion(
    session: Session,
    opinion_id: int,
    opinion_cluster_id: int,
    person_positions: bool = False,
    download_local_file: bool = False,
    no_update: bool = False,
):
    """Download opinion data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param opinion_id: opinion id to clone
    :param opinion_cluster_id: cluster id related to opinions
    :param person_positions: True if we should clone person positions
    :param download_local_file: True if we should download local_path file
    :param no_update: If True, skip updating object if it already exists
    :return:
    """

    opinion_path = reverse(
        "opinion-detail",
        kwargs={"version": "v4", "pk": opinion_id},
    )
    opinion_url = f"{DOMAIN}{opinion_path}"

    if no_update and Opinion.objects.filter(pk=opinion_id).exists():
        opinion = Opinion.objects.get(pk=opinion_id)
        print(f"Opinion already exists: {opinion_id}")
        return opinion

    print(f"Cloning opinion id: {opinion_id}")

    op_data = get_json_data(opinion_url, session)
    author = op_data.pop("author", None)
    main_version = op_data.pop("main_version")
    local_path = op_data.pop("local_path")
    joined_by_urls = op_data.pop("joined_by", [])

    # Delete fields with fk or m2m relations or unneeded fields
    clean_api_data(op_data, ["opinions_cited", "cluster", "main_version"])

    if author is not None:
        cloned_person = clone_person(
            session, [get_id_from_url(author)], person_positions, no_update
        )

        if cloned_person:
            # Add id of cloned person
            op_data["author"] = cloned_person[0]

    if main_version:
        # Get opinion id of main opinion
        main_version_id = int(main_version.split("/")[-2])
        try:
            _ = Opinion.objects.get(pk=main_version_id)
        except Opinion.DoesNotExist:
            clone_opinion(
                session,
                main_version_id,
                opinion_cluster_id,
                person_positions,
                download_local_file,
            )

        op_data["main_version_id"] = main_version_id

    op_data["cluster_id"] = opinion_cluster_id

    # Create opinion
    op, created = Opinion.objects.update_or_create(
        id=op_data["id"], defaults=op_data
    )

    joined_by_ids = [get_id_from_url(j) for j in joined_by_urls]
    if joined_by_ids:
        clone_person(session, joined_by_ids, person_positions, no_update)

    if download_local_file and local_path:
        file_url = f"{LOCAL_PATH_DOMAIN}/{local_path}"
        response = requests.get(file_url)
        if response.status_code != 200:
            print(f"Failed to download: {file_url}")
            return op
        filename = local_path.split("/")[-1]
        file_content = ContentFile(response.content)
        try:
            op.local_path.save(filename, file_content, save=True)
            print(f"local_path file saved to {op.local_path.url}")
        except ClientError:
            print(
                ">> Can't download file, check that your API keys are set and not expired to save the file."
            )
            pass

    action = "Created" if created else "Updated"
    print(f"({action}) Opinion id: {op.pk}")

    return op


def clone_docket(
    session: Session,
    docket_ids: list,
    add_docket_entries: bool,
    add_audio_files: bool,
    add_clusters: bool,
    person_positions: bool = False,
    download_local_file: bool = False,
    no_update: bool = False,
):
    """Download docket data from courtlistener.com and add it to local
    environment

    :param session: a Requests session
    :param docket_ids: a list of docket ids
    :param add_docket_entries: flag to clone docket entries and recap docs
    :param add_audio_files: flag to clone related audio files
        when cloning a docket
    :param add_clusters: flag to clone related opinion clusters when
        cloning a docket
    :param person_positions: True is we should clone person positions
    :param download_local_file: True if we should download local_path file from opinion when add_clusters is True
    :param no_update: If True, skip updating object if it already exists
    :return: list of docket objects
    """

    dockets = []

    for docket_id in docket_ids:
        print(f"Cloning docket id: {docket_id}")

        if no_update and Docket.objects.filter(pk=docket_id).exists():
            docket = Docket.objects.get(pk=docket_id)
            dockets.append(docket)
            print(
                "Docket already exists here:",
                reverse("view_docket", args=[docket.pk, docket.slug]),
            )
            if add_docket_entries:
                clone_docket_entries(session, docket_id, no_update)
            continue

        docket_path = reverse(
            "docket-detail",
            kwargs={"version": "v4", "pk": docket_id},
        )
        docket_url = f"{DOMAIN}{docket_path}"

        # Get and clean docket data
        docket_data = get_json_data(docket_url, session)

        audio_files_urls = docket_data.pop("audio_files", [])
        cluster_urls = docket_data.pop("clusters", [])

        # Remove unneeded fields
        clean_api_data(
            docket_data, ["original_court_info", "tags", "panel", "idb_data"]
        )

        with transaction.atomic():
            if docket_data.get("court"):
                court_id = get_id_from_url(docket_data["court"])
                docket_data["court"] = clone_court(
                    session, [court_id], no_update
                )[0]

            if docket_data.get("appeal_from"):
                af_id = get_id_from_url(docket_data["appeal_from"])
                docket_data["appeal_from"] = clone_court(
                    session, [af_id], no_update
                )[0]

            for field in ["assigned_to", "referred_to"]:
                if docket_data.get(field):
                    pid = get_id_from_url(docket_data[field])
                    docket_data[field] = clone_person(
                        session, [pid], person_positions, no_update
                    )[0]

            docket, created = Docket.objects.update_or_create(
                id=docket_data["id"], defaults=docket_data
            )

            if add_audio_files:
                audio_files_ids = [
                    get_id_from_url(a) for a in audio_files_urls
                ]
                clone_audio_files(session, audio_files_ids, no_update)

            if add_clusters:
                c_ids = [get_id_from_url(c) for c in cluster_urls]
                clone_opinion_cluster(
                    session,
                    c_ids,
                    download_cluster_files=False,
                    add_docket_entries=False,
                    person_positions=person_positions,
                    download_opinion_files=download_local_file,
                    no_update=no_update,
                )

            if add_docket_entries:
                clone_docket_entries(session, docket_id, no_update)

            action = "Created" if created else "Updated"
            print(
                f"({action}) View cloned docket here: {reverse('view_docket', args=[docket_data['id'], docket_data['slug']])}"
            )
            dockets.append(docket)

    return dockets


def clone_audio_files(
    session: Session, audio_files: list[str], no_update: bool = False
):
    """Clone audio_audio rows related to the docket
    Also, clone the actual `local_mp3_path` files to the dev storage.
    This is useful for testing the audio.transcribe command

    :param session: session with authorization header
    :param audio_files: api urls for the audio files
    :param no_update: If True, skip updating object if it already exists
    """

    for audio_id in audio_files:
        print(f"Cloning Audio id: {audio_id}")

        if no_update and Audio.objects.filter(pk=audio_id).exists():
            audio = Audio.objects.get(pk=audio_id)
            print(
                "Audio already exists here:",
                reverse("view_audio_file", args=[audio_id, audio.docket.slug]),
            )
            continue

        audio_path = reverse(
            "audio-detail",
            kwargs={"version": "v4", "pk": audio_id},
        )
        audio_url = f"{DOMAIN}{audio_path}"
        audio_json = get_json_data(audio_url, session)

        docket_url = audio_json.get("docket")
        if docket_url:
            docket_id = get_id_from_url(docket_url)
            if Docket.objects.filter(pk=docket_id).exists():
                docket = Docket.objects.get(pk=docket_id)
            else:
                docket = clone_docket(
                    session,
                    [docket_id],
                    add_docket_entries=False,
                    add_audio_files=False,
                    add_clusters=False,
                    person_positions=False,
                    download_local_file=False,
                    no_update=no_update,
                )[0]
            audio_json["docket"] = docket
        else:
            audio_json["docket"] = None

        clean_api_data(audio_json, ["panel", "stt_google_response"])

        if not audio_json.get("stt_transcript"):
            audio_json["stt_transcript"] = ""

        local_path_mp3 = audio_json.pop("local_path_mp3", None)

        audio, created = Audio.objects.update_or_create(
            id=audio_json["id"], defaults=audio_json
        )

        if local_path_mp3:
            if (
                not audio.local_path_mp3
                or not audio.local_path_mp3.storage.exists(
                    audio.local_path_mp3.name
                )
            ):
                print("Download, file doesnt exist in local storage")
                try:
                    _, year, month, day, _ = local_path_mp3.split("/")
                    file_with_date = datetime(int(year), int(month), int(day))
                    # Set this attribute on the instance so make_upload_path can use it
                    setattr(audio, "file_with_date", file_with_date.date())

                    prod_url = f"{PROD_STORAGE_PATH}/{local_path_mp3}"
                    print(f"Downloading MP3 from {prod_url}")

                    r = requests.get(prod_url, stream=True)
                    if r.status_code == 200:
                        filename = local_path_mp3.split("/")[-1]
                        audio.local_path_mp3.save(
                            filename, ContentFile(r.content), save=True
                        )
                except Exception as e:
                    print(f"Failed to download audio file: {e}")

        action = "Created" if created else "Updated"
        print(
            f"({action}) View cloned audio here: {reverse('view_audio_file', args=[audio_id, audio.docket.slug])}"
        )


def clone_docket_entries(
    session: Session, docket_id: int, no_update: bool = False
) -> list:
    """Download docket entries data from courtlistener.com and add it to local
    environment

    :param session: a Requests session
    :param docket_id: docket id to clone docket entries
    :param no_update: If True, skip updating object if it already exists
    :return: list of docket objects
    """

    params = {"docket__id": docket_id}

    docket_entries_data = []
    created_docket_entries = []

    docket_entry_path = reverse(
        "docketentry-list",
        kwargs={"version": "v4"},
    )

    # Get list of docket entries using docket id
    docket_entry_list_url = f"{DOMAIN}{docket_entry_path}"
    docket_entry_list_request = session.get(
        docket_entry_list_url, timeout=120, params=params
    )

    if docket_entry_list_request.status_code == 403:
        # You don't have the required permissions to view docket entries in api
        raise CloneException(
            "You don't have the required permissions to clone Docket entries."
        )

    docket_entry_list_data = docket_entry_list_request.json()
    docket_entries_data.extend(docket_entry_list_data.get("results", []))
    docket_entry_next_url = docket_entry_list_data.get("next")

    while docket_entry_next_url:
        docket_entry_list_data = get_json_data(docket_entry_next_url, session)
        docket_entry_next_url = docket_entry_list_data.get("next")
        docket_entries_data.extend(docket_entry_list_data.get("results", []))

    for docket_entry_data in docket_entries_data:
        if (
            no_update
            and DocketEntry.objects.filter(pk=docket_entry_data["id"]).exists()
        ):
            continue

        recap_documents_data = docket_entry_data.get("recap_documents")
        tags_data = docket_entry_data.get("tags")

        # Remove unneeded fields
        clean_api_data(
            docket_entry_data, ["docket", "recap_documents", "tags"]
        )

        docket_entry_data["docket_id"] = docket_id

        with transaction.atomic():
            # Create/update docket entry
            docket_entry, created = DocketEntry.objects.update_or_create(
                id=docket_entry_data.get("id"), defaults=docket_entry_data
            )
            action = "Created" if created else "Updated"
            print(f"({action}) Docket entry id: {docket_entry.pk}")

            # Clone recap documents
            clone_recap_documents(
                session, docket_entry.pk, recap_documents_data, no_update
            )
            # Create tags for docket entry
            cloned_tags = clone_tag(
                session, [get_id_from_url(tag_url) for tag_url in tags_data]
            )

            if cloned_tags:
                docket_entry.tags.add(*cloned_tags)

            created_docket_entries.append(docket_entry)

    return created_docket_entries


def clone_recap_documents(
    session: Session,
    docket_entry_id: int,
    recap_documents_data: list,
    no_update: bool = False,
) -> list:
    """Download recap documents data from courtlistener.com and add it to local
    environment

    :param session: a Requests session
    :param docket_entry_id: docket entry id to assign to recap document
    :param recap_documents_data: list with recap documents data to create
    :param no_update: If True, skip updating object if it already exists
    :return: list of recap documents objects
    """
    created_recap_documents = []
    for recap_document_data in recap_documents_data:
        if (
            no_update
            and RECAPDocument.objects.filter(
                pk=recap_document_data["id"]
            ).exists()
        ):
            print(
                "Recap document already exists here:",
                reverse(
                    "recapdocument-detail",
                    args=["v4", recap_document_data["id"]],
                ),
            )
            continue

        tags_data = recap_document_data.pop("tags", [])

        # Remove unneeded fields
        clean_api_data(recap_document_data)

        recap_document_data["docket_entry_id"] = docket_entry_id

        recap_document, created = RECAPDocument.objects.update_or_create(
            id=recap_document_data.get("id"), defaults=recap_document_data
        )

        # Create and add tags
        cloned_tags = clone_tag(
            session, [get_id_from_url(tag_url) for tag_url in tags_data]
        )

        if cloned_tags:
            recap_document.tags.set(*cloned_tags)

        created_recap_documents.append(recap_document)

        action = "Created" if created else "Updated"
        print(
            f"({action}) View cloned recap document here: {reverse('recapdocument-detail', args=['v4', recap_document_data['id']])}"
        )

    return created_recap_documents


def clone_tag(session: Session, tag_ids: list) -> list:
    """Clone tags from docket entries or recap documents

    :param session: a Requests session
    :param tag_ids: list of tag ids to clone
    :return:
    """
    created_tags = []
    for tag_id in tag_ids:
        print(f"Cloning tag id: {tag_id}")

        try:
            tag = Tag.objects.get(pk=tag_id)
            print(
                f"Tag id: {tag_id} already exists",
            )
            created_tags.append(tag)
            continue
        except Tag.DoesNotExist:
            pass

        # Create tag
        tag_path = reverse(
            "tag-detail",
            kwargs={"version": "v4", "pk": tag_id},
        )
        tag_url = f"{DOMAIN}{tag_path}"
        tag_data = get_json_data(tag_url, session)

        del tag_data["resource_uri"]

        try:
            tag, created = Tag.objects.get_or_create(**tag_data)
        except (IntegrityError, ValidationError):
            tag = Tag.objects.filter(pk=tag_data["id"])[0]

        if tag:
            created_tags.append(tag)

            print(
                "View cloned tag here:",
                reverse("tag-detail", args=["v4", tag_id]),
            )

    return created_tags


def clone_position(
    session: Session,
    position_ids: list,
    person_id: int,
    no_update: bool = False,
):
    """Download position data from courtlistener.com and add it to local environment

    :param session: a Requests session
    :param position_ids: a list of position ids
    :param person_id: id of the person the positions belong to
    :param no_update: If True, skip updating object if it already exists
    :return: list of position objects
    """
    positions = []

    for position_id in position_ids:
        print(f"Cloning position id: {position_id}")

        if no_update and Position.objects.filter(pk=position_id).exists():
            continue

        # Create position
        position_path = reverse(
            "position-detail",
            kwargs={"version": "v4", "pk": position_id},
        )
        position_url = f"{DOMAIN}{position_path}"
        position_data = get_json_data(position_url, session)

        # delete unneeded fields
        clean_api_data(
            position_data,
            [
                "retention_events",
                "person",
                "supervisor",
                "predecessor",
                "school",
                "appointer",
            ],
        )

        # Prepare values
        for field in [
            "date_nominated",
            "date_elected",
            "date_recess_appointment",
            "date_referred_to_judicial_committee",
            "date_judicial_committee_action",
            "date_hearing",
            "date_confirmation",
            "date_start",
            "date_termination",
            "date_retirement",
        ]:
            if position_data[field]:
                position_data[field] = parse_date(position_data[field])

        position_data["court"] = (
            clone_court(session, [position_data["court"].get("id")])[0]
            if position_data.get("court")
            else None
        )

        position_data["person_id"] = person_id

        pos, created = Position.objects.update_or_create(
            id=position_data["id"], defaults=position_data
        )

        positions.append(pos)

        action = "Created" if created else "Updated"
        print(
            f"({action}) View cloned position here: {reverse('position-detail', args=['v4', position_id])}"
        )

    return positions


def clone_person(
    session: Session,
    people_ids: list,
    positions: bool = False,
    no_update: bool = False,
):
    """Download person data from courtlistener.com and add it to local
    environment

    :param session: a Requests session
    :param people_ids: a list of person ids
    :param positions: True if we should clone person positions
    :param no_update: If True, skip updating a Person object if it already exists, unless positions cloning is enabled
    :return: list of person objects
    """

    people = []

    for person_id in people_ids:
        print(f"Cloning person id: {person_id}")

        person_exists = Person.objects.filter(pk=person_id).exists()

        if no_update and person_exists and not positions:
            print(
                "Person already exists here:",
                reverse("person-detail", args=["v4", person_id]),
            )
            people.append(Person.objects.get(pk=person_id))
            continue

        people_path = reverse(
            "person-detail",
            kwargs={"version": "v4", "pk": person_id},
        )

        person_url = f"{DOMAIN}{people_path}"
        person_data = get_json_data(person_url, session)

        positions_urls = person_data.pop("positions", [])

        # delete unneeded fields
        clean_api_data(
            person_data,
            [
                "aba_ratings",
                "race",
                "sources",
                "educations",
                "political_affiliations",
                "is_alias_of",
            ],
        )

        # Prepare some values
        if person_data.get("date_dob"):
            person_data["date_dob"] = parse_date(person_data["date_dob"])
        if person_data.get("date_dod"):
            person_data["date_dod"] = parse_date(person_data["date_dod"])
        if person_data.get("religion"):
            person_data["religion"] = next(
                (
                    k
                    for k, v in Person.RELIGIONS
                    if v == person_data["religion"]
                ),
                "",
            )

        if not (no_update and person_exists):
            person, created = Person.objects.update_or_create(
                id=person_data["id"], defaults=person_data
            )
            action = "Created" if created else "Updated"
            print(
                f"({action}) View cloned person here: {reverse('person-detail', args=['v4', person.pk])}"
            )
            people.append(person)
        else:
            print(
                f"Person {person_id} exists here: {reverse('person-detail', args=['v4', person_id])}. Skipping (but checking positions)."
            )
            people.append(Person.objects.get(pk=person_id))

        # Clone positions if requested
        if positions and positions_urls:
            position_ids = [get_id_from_url(p) for p in positions_urls if p]
            clone_position(session, position_ids, person_id, no_update)

    return people


def clone_court(session: Session, court_ids: list, no_update: bool = False):
    """Download court data from courtlistener.com and add it to local
    environment

    :param session: a Requests session
    :param court_ids: list of court ids
    :param no_update: If True, skip updating object if it already exists
    :return: list of Court objects
    """

    courts = []

    for court_id in court_ids:
        print(f"Cloning court id: {court_id}")

        if no_update and Court.objects.filter(pk=court_id).exists():
            print(
                "Court already exists here:",
                reverse("court-detail", args=["v4", court_id]),
            )
            courts.append(Court.objects.get(pk=court_id))
            continue

        # Create court
        court_path = reverse(
            "court-detail",
            kwargs={"version": "v4", "pk": court_id},
        )
        court_url = f"{DOMAIN}{court_path}"
        court_data = get_json_data(court_url, session)

        parent_court_url = court_data.pop("parent_court", None)
        appeals_to_urls = court_data.pop("appeals_to", [])

        # Recursive clone of parent
        parent_court = None
        if parent_court_url is not None:
            parent_id = get_id_from_url(parent_court_url)
            parent_court = clone_court(session, [parent_id], no_update)[0]

        appeals_to_ids = [get_id_from_url(url) for url in appeals_to_urls]
        if appeals_to_ids:
            clone_court(session, appeals_to_ids, no_update)

        clean_api_data(court_data)
        court_data["parent_court"] = parent_court

        court, created = Court.objects.update_or_create(
            id=court_data["id"], defaults=court_data
        )

        if appeals_to_ids:
            court.appeals_to.set(Court.objects.filter(id__in=appeals_to_ids))

        action = "Created" if created else "Updated"
        print(
            f"({action}) View court here: {reverse('court-detail', args=['v4', court_id])}"
        )
        courts.append(court)

    return courts


class Command(BaseCommand):
    help = (
        "Clone data from CourtListener.com into dev environment. It "
        "requires to set CL_API_TOKEN varible in the .env file."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = None
        self.ids = []

        self.s = requests.session()
        self.s.headers = {
            "Authorization": f"Token {os.environ.get('CL_API_TOKEN', '')}"
        }

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=VALID_TYPES,
            help="Object type to clone. Current choices are {}".format(
                ", ".join(VALID_TYPES)
            ),
            required=True,
        )

        parser.add_argument(
            "--id",
            dest="ids",
            nargs="+",
            help="Object id to clone, you can get it from courtlistener.com "
            "urls (e.g. in "
            "https://www.courtlistener.com/opinion/771797/rupinder-kaur"
            "-loveleen-kaur-v-immigration-and-naturalization-service/ "
            "the id is 771797).",
            required=True,
        )

        parser.add_argument(
            "--download-cluster-files",
            action="store_true",
            default=False,
            help="Use this flag to download json file from "
            "filepath_json_harvard field",
        )

        parser.add_argument(
            "--download-opinion-files",
            action="store_true",
            default=False,
            help="Use this flag to download file from local_path field",
        )

        parser.add_argument(
            "--add-docket-entries",
            action="store_true",
            default=False,
            help="Use this flag to clone docket entries when cloning clusters."
            " It will update docket entries and RECAP documents if the Docket "
            "already exists. The API token must have RECAP permissions or it "
            "will raise a 403 error.",
        )

        parser.add_argument(
            "--add-audio-files",
            action="store_true",
            default=False,
            help="Use this flag to clone docket audio files when cloning "
            "a docket.",
        )

        parser.add_argument(
            "--add-clusters",
            action="store_true",
            default=False,
            help="Use this flag to clone docket clusters when cloning "
            "a docket.",
        )

        parser.add_argument(
            "--clone-person-positions",
            action="store_true",
            default=False,
            help="Use this flag to clone person positions. This will make more API "
            "calls.",
        )
        parser.add_argument(
            "--no-update",
            action="store_true",
            default=False,
            help="Do not update existing objects.",
        )

    def handle(self, *args, **options):
        self.type = options.get("type")
        self.ids = options.get("ids")
        download_cluster_files = options.get("download_cluster_files")
        download_opinion_files = options.get("download_opinion_files")
        add_docket_entries = options.get("add_docket_entries")
        clone_person_positions = options.get("clone_person_positions")
        no_update = options.get("no_update")

        if not os.environ.get("CL_API_TOKEN"):
            self.stdout.write("Error: CL_API_TOKEN not set in .env file")
            return

        if not settings.DEVELOPMENT:
            self.stdout.write(
                "Error: Command not enabled for production environment"
            )
            return

        if options["download_opinion_files"]:
            required_keys = [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
            ]
            missing_keys = [k for k in required_keys if not os.environ.get(k)]
            if missing_keys:
                self.stderr.write(
                    self.style.ERROR(
                        f"Error: The following AWS keys are required for --download-opinion-files: "
                        f"{', '.join(missing_keys)}"
                    )
                )
                return

        match self.type:
            case "search.OpinionCluster":
                clone_opinion_cluster(
                    self.s,
                    self.ids,
                    download_cluster_files,
                    add_docket_entries,
                    clone_person_positions,
                    download_opinion_files,
                    no_update,
                )
            case "search.Docket":
                clone_docket(
                    self.s,
                    self.ids,
                    add_docket_entries,
                    options["add_audio_files"],
                    options["add_clusters"],
                    clone_person_positions,
                    download_opinion_files,
                    no_update,
                )
            case "people_db.Person":
                clone_person(
                    self.s,
                    self.ids,
                    clone_person_positions,
                    no_update,
                )
            case "search.Court":
                clone_court(
                    self.s,
                    self.ids,
                    no_update,
                )
            case "audio.Audio":
                clone_audio_files(
                    self.s,
                    self.ids,
                    no_update,
                )
            case _:
                self.stdout.write("Invalid type!")
