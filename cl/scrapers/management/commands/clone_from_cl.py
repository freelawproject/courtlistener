"""
This tool allows you to partially clone data from courtlistener.com to your
local environment, you only need to pass the type and object id and run it.

manage.py clone_from_cl --type search.Opinion --id 9355884
manage.py clone_from_cl --type search.Docket --id 5377675
manage.py clone_from_cl --type people_db.Person --id 16207
manage.py clone_from_cl --type search,Court --id usnmcmilrev

This tool is only for development purposes, so it only works when
the DEVELOPMENT env is set to True. It also relies on the CL_API_TOKEN
env variable.

You can also pass the api token before running the command:

CL_API_TOKEN='my_api_key' manage.py clone_from_cl --type search.Opinion --id 9355884

You can also clone multiple objects at the same time, for example:

manage.py clone_from_cl --type search.OpinionCluster --id 1867834 1867833
manage.py clone_from_cl --type search.Docket --id 14614371 5377675
manage.py clone_from_cl --type search.Court --id mspb leechojibtr
manage.py clone_from_cl --type people_db.Person --id 16212 16211

This is still work in progress, some data is not cloned yet.
"""
import json
import os
import pathlib

import requests
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import BaseCommand
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.dateparse import parse_date
from requests import Session

from cl.people_db.models import Person
from cl.search.models import Citation, Opinion, RECAPDocument
from cl.search.tasks import add_items_to_solr

VALID_TYPES = (
    "search.OpinionCluster",
    "search.Docket",
    "people_db.Person",
    "search.Court",
)

domain = "https://www.courtlistener.com"


class CloneException(Exception):
    """Error found in clone process."""

    def __init__(self, message: str) -> None:
        self.message = message


def get_id_from_url(api_url: str) -> str:
    """Get the PK from an API url"""
    return api_url.split("/")[-2]


def clone_opinion_cluster(
    session: Session,
    cluster_ids: list,
    download_cluster_files: bool,
    add_docket_entries: bool,
    object_type="search.OpinionCluster",
):
    """Download opinion cluster data from courtlistener.com and add it to
    local environment
    :param session: a Requests session
    :param cluster_ids: a list of opinion cluster ids
    :param download_cluster_files: True if it should download cluster files
    :param add_docket_entries: flag to clone docket entries and recap docs
    :param object_type: OpinionCluster app name with model name
    :return: list of opinion cluster objects
    """

    opinion_clusters = []

    for cluster_id in cluster_ids:
        print(f"Cloning opinion cluster id: {cluster_id}")
        model = apps.get_model(object_type)

        try:
            opinion_cluster = model.objects.get(pk=int(cluster_id))
            print(
                "Opinion cluster already exists here:",
                reverse(
                    "view_case",
                    args=[opinion_cluster.pk, opinion_cluster.docket.slug],
                ),
            )
            opinion_clusters.append(opinion_cluster)
            continue
        except model.DoesNotExist:
            pass

        cluster_path = reverse(
            "opinioncluster-detail",
            kwargs={"version": "v3", "pk": cluster_id},
        )
        cluster_url = f"{domain}{cluster_path}"
        cluster_datum = session.get(cluster_url, timeout=120).json()
        docket_id = get_id_from_url(cluster_datum["docket"])
        docket = clone_docket(session, [docket_id], add_docket_entries)[0]
        citation_data = cluster_datum["citations"]
        panel_data = cluster_datum["panel"]
        non_participating_judges_data = cluster_datum[
            "non_participating_judges"
        ]
        sub_opinions_data = cluster_datum["sub_opinions"]
        # delete unneeded fields
        for f in [
            "resource_uri",
            "docket",
            "citations",
            "sub_opinions",
            "absolute_url",
            "panel",
            "non_participating_judges",
        ]:
            del cluster_datum[f]

        # Assign docket pk in cluster data
        cluster_datum["docket_id"] = docket.pk

        json_harvard = None
        json_path = None

        if download_cluster_files:
            if cluster_datum.get("filepath_json_harvard"):
                try:
                    ia_url = cluster_datum.get(
                        "filepath_json_harvard"
                    ).replace(
                        "/storage/harvard_corpus/",
                        "https://archive.org/download/",
                    )

                    req = requests.get(
                        ia_url, allow_redirects=True, timeout=120
                    )

                    if req.status_code == 200:
                        print(f"Downloading {ia_url}")
                        json_harvard = json.dumps(req.json(), indent=4)
                        path = pathlib.PurePath(
                            cluster_datum.get("filepath_json_harvard")
                        )
                        json_path = os.path.join(
                            "harvard_corpus", path.parent.name, path.name
                        )

                except Exception:
                    print(
                        f"Can't download filepath_json_harvard file for "
                        f"cluster id: {cluster_id}"
                    )

        # Clone panel data
        panel_data_ids = [
            get_id_from_url(person_url) for person_url in panel_data
        ]
        added_panel_ids = []

        if panel_data_ids:
            added_panel_ids.extend(clone_person(session, panel_data_ids))

        # Clone non participating judges data
        non_participating_judges_data_ids = [
            get_id_from_url(person_url)
            for person_url in non_participating_judges_data
        ]
        added_non_participating_judges_data_ids = []

        if non_participating_judges_data_ids:
            added_non_participating_judges_data_ids.extend(
                clone_person(session, non_participating_judges_data_ids)
            )

        # Clone opinions
        prepared_opinion_data = []
        added_opinions_ids = []

        for op in sub_opinions_data:
            # Get opinion from api
            op_data = session.get(op, timeout=120).json()
            author = op_data["author"]

            # Delete fields with fk or m2m relations or unneeded fields
            for f in [
                "opinions_cited",
                "cluster",
                "absolute_url",
                "resource_uri",
                "author",
                "joined_by",
            ]:
                del op_data[f]

            if author:
                cloned_person = clone_person(
                    session, [get_id_from_url(author)]
                )

                if cloned_person:
                    # Add id of cloned person
                    op_data["author"] = cloned_person[0]

            # Append new data
            prepared_opinion_data.append(op_data)

        with transaction.atomic():
            # Create opinion cluster
            opinion_cluster = model.objects.create(**cluster_datum)

            if added_panel_ids:
                opinion_cluster.panel.add(
                    *Person.objects.filter(id__in=added_panel_ids)
                )

            if added_non_participating_judges_data_ids:
                opinion_cluster.non_participating_judges.add(
                    *Person.objects.filter(
                        id__in=added_non_participating_judges_data_ids
                    )
                )

            if download_cluster_files:
                if json_harvard and json_path:
                    opinion_cluster.filepath_json_harvard.save(
                        json_path, ContentFile(json_harvard)
                    )

            for cite_data in citation_data:
                # Create citations
                cite_data["cluster_id"] = opinion_cluster.pk
                Citation.objects.create(**cite_data)

            for opinion_data in prepared_opinion_data:
                # Update cluster_id in opinion's json
                opinion_data["cluster_id"] = opinion_cluster.pk

                # Create opinion
                op = Opinion.objects.create(**opinion_data)

                # Store created opinion id
                added_opinions_ids.append(op.id)

            opinion_clusters.append(opinion_cluster)
            print(
                "View cloned case here:",
                reverse("view_case", args=[opinion_cluster.pk, docket.slug]),
            )

        # Add opinions to search engine
        add_items_to_solr.delay(added_opinions_ids, "search.Opinion")

    # Add opinion clusters to search engine
    add_items_to_solr.delay(
        [oc.pk for oc in opinion_clusters], "search.OpinionCluster"
    )

    return opinion_clusters


def clone_docket(
    session: Session,
    docket_ids: list,
    add_docket_entries: bool,
    object_type="search.Docket",
):
    """Download docket data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param docket_ids: a list of docket ids
    :param add_docket_entries: flag to clone docket entries and recap docs
    :param object_type: Docket app name with model name
    :return: list of docket objects
    """

    dockets = []

    for docket_id in docket_ids:
        print(f"Cloning docket id: {docket_id}")

        model = apps.get_model(object_type)

        try:
            docket = model.objects.get(pk=docket_id)
            print(
                "Docket already exists here:",
                reverse("view_docket", args=[docket.pk, docket.slug]),
            )
            dockets.append(docket)

            if add_docket_entries:
                clone_docket_entries(session, docket.pk)

            continue
        except model.DoesNotExist:
            pass

        # Create new Docket
        docket_path = reverse(
            "docket-detail",
            kwargs={"version": "v3", "pk": docket_id},
        )
        docket_url = f"{domain}{docket_path}"
        docket_data = session.get(docket_url, timeout=120).json()

        # Remove unneeded fields
        for f in [
            "resource_uri",
            "original_court_info",
            "absolute_url",
            "clusters",
            "audio_files",
            "tags",
            "panel",
        ]:
            del docket_data[f]

        with transaction.atomic():
            # Get or create required objects
            docket_data["court"] = (
                clone_court(session, [get_id_from_url(docket_data["court"])])[
                    0
                ]
                if docket_data["court"]
                else None
            )

            docket_data["appeal_from"] = (
                clone_court(
                    session, [get_id_from_url(docket_data["appeal_from"])]
                )[0]
                if docket_data["appeal_from"]
                else None
            )

            docket_data["assigned_to"] = (
                clone_person(
                    session, [get_id_from_url(docket_data["assigned_to"])]
                )[0]
                if docket_data["assigned_to"]
                else None
            )

            docket = model.objects.create(**docket_data)

            dockets.append(docket)

            if add_docket_entries:
                clone_docket_entries(session, docket.pk)

            print(
                "View cloned docket here:",
                reverse(
                    "view_docket",
                    args=[docket_data["id"], docket_data["slug"]],
                ),
            )

    # Add dockets to search engine
    add_items_to_solr.delay([doc.pk for doc in dockets], "search.Docket")

    return dockets


def clone_docket_entries(
    session: Session, docket_id: int, object_type="search.DocketEntry"
) -> list:
    """Download docket entries data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param docket_id: docket id to clone docket entries
    :param object_type: Docket app name with model name
    :return: list of docket objects
    """

    params = {"docket__id": docket_id}

    docket_entries_data = []
    created_docket_entries = []

    docket_entry_path = reverse(
        "docketentry-list",
        kwargs={"version": "v3"},
    )

    # Get list of docket entries using docket id
    docket_entry_list_url = f"{domain}{docket_entry_path}"
    docket_entry_list_request = session.get(
        docket_entry_list_url, timeout=120, params=params
    )
    docket_entry_list_data = docket_entry_list_request.json()

    if docket_entry_list_request.status_code == 403:
        # You don't have the required permissions to view docket entries in api
        raise CloneException(
            "You don't have the required permissions to "
            "clone Docket entries."
        )

    docket_entries_data.extend(docket_entry_list_data.get("results", []))
    docket_entry_next_url = docket_entry_list_data.get("next")

    while docket_entry_next_url:
        docket_entry_list_request = session.get(
            docket_entry_next_url, timeout=120
        )
        docket_entry_list_data = docket_entry_list_request.json()
        docket_entry_next_url = docket_entry_list_data.get("next")
        docket_entries_data.extend(docket_entry_list_data.get("results", []))

    model = apps.get_model(object_type)

    for docket_entry_data in docket_entries_data:
        recap_documents_data = docket_entry_data.get("recap_documents")
        tags_data = docket_entry_data.get("tags")

        # Remove unneeded fields
        for f in [
            "resource_uri",
            "docket",
            "recap_documents",
            "tags",
        ]:
            del docket_entry_data[f]

        docket_entry_data["docket_id"] = docket_id

        with transaction.atomic():
            # Create docket entry
            docket_entry = model.objects.create(**docket_entry_data)
            print(f"Docket entry id: {docket_entry.pk} cloned")

            # Clone recap documents
            clone_recap_documents(
                session, docket_entry.pk, recap_documents_data
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
    session: Session, docket_entry_id: int, recap_documents_data: list
) -> list:
    """Download recap documents data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param docket_entry_id: docket entry id to assign to recap document
    :param recap_documents_data: list with recap documents data to create
    :return: list of recap documents objects
    """
    created_recap_documents = []
    for recap_document_data in recap_documents_data:
        tags_data = recap_document_data.get("tags")

        # Remove unneeded fields
        for f in [
            "resource_uri",
            "tags",
            "absolute_url",
        ]:
            del recap_document_data[f]

        recap_document_data["docket_entry_id"] = docket_entry_id

        recap_document = RECAPDocument.objects.create(**recap_document_data)

        # Create and add tags
        cloned_tags = clone_tag(
            session, [get_id_from_url(tag_url) for tag_url in tags_data]
        )

        if cloned_tags:
            recap_document.tags.add(*cloned_tags)

        created_recap_documents.append(recap_document)

    return created_recap_documents


def clone_tag(
    session: Session, tag_ids: list, object_type="search.Tag"
) -> list:
    """Clone tags from docket entries or recap documents
    :param session: a Requests session
    :param tag_ids: list of tag ids to clone
    :param object_type: Tag app name with model name
    :return:
    """
    created_tags = []
    for tag_id in tag_ids:
        print(f"Cloning tag id: {tag_id}")

        model = apps.get_model(object_type)

        try:
            tag = model.objects.get(pk=tag_id)
            print(
                f"Tag id: {tag_id} already exists",
            )
            created_tags.append(tag)
            continue
        except model.DoesNotExist:
            pass

        # Create tag
        tag_path = reverse(
            "tag-detail",
            kwargs={"version": "v3", "pk": tag_id},
        )
        tag_url = f"{domain}{tag_path}"
        tag_data = session.get(tag_url, timeout=120).json()

        del tag_data["resource_uri"]

        try:
            tag, created = model.objects.get_or_create(**tag_data)
        except (IntegrityError, ValidationError):
            tag = model.objects.filter(pk=tag_data["id"])[0]

        created_tags.append(tag)

        print(
            "View cloned tag here:",
            reverse("tag-detail", args=["v3", tag_id]),
        )

    return created_tags


def clone_person(
    session: Session, people_ids: list, object_type="people_db.Person"
):
    """Download person data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param people_ids: a list of person ids
    :param object_type: Person app name with model name
    :return: list of person objects
    """

    people = []

    for person_id in people_ids:
        print(f"Cloning person id: {person_id}")

        model = apps.get_model(object_type)

        try:
            person = model.objects.get(pk=person_id)
            print(
                "Person already exists here:",
                reverse("person-detail", args=["v3", person.pk]),
            )
            people.append(person)
            continue
        except model.DoesNotExist:
            pass

        # Create person
        people_path = reverse(
            "person-detail",
            kwargs={"version": "v3", "pk": person_id},
        )
        person_url = f"{domain}{people_path}"
        person_data = session.get(person_url, timeout=120).json()
        # delete unneeded fields
        for f in [
            "resource_uri",
            "aba_ratings",
            "race",
            "sources",
            "educations",
            "positions",
            "political_affiliations",
        ]:
            del person_data[f]
        # Prepare some values
        if person_data["date_dob"]:
            person_data["date_dob"] = parse_date(person_data["date_dob"])
        try:
            person, created = model.objects.get_or_create(**person_data)
        except (IntegrityError, ValidationError):
            person = model.objects.filter(pk=person_data["id"])[0]

        people.append(person)

        print(
            "View cloned person here:",
            reverse("person-detail", args=["v3", person_id]),
        )

    # Add people to search engine
    add_items_to_solr.delay(
        [person.pk for person in people], "people_db.Person"
    )

    return people


def clone_court(session: Session, court_ids: list, object_type="search.Court"):
    """Download court data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param court_ids: list of court ids
    :param object_type: Court app name with model name
    :return: list of Court objects
    """

    courts = []

    for court_id in court_ids:
        print(f"Cloning court id: {court_id}")

        model = apps.get_model(object_type)

        try:
            ct = model.objects.get(pk=court_id)
            courts.append(ct)
            print(
                "Court already exists here:",
                reverse("court-detail", args=["v3", ct.pk]),
            )
            continue
        except model.DoesNotExist:
            pass

        # Create court
        court_path = reverse(
            "court-detail",
            kwargs={"version": "v3", "pk": court_id},
        )
        court_url = f"{domain}{court_path}"
        court_data = session.get(court_url, timeout=120).json()
        # delete resource_uri value generated by DRF
        del court_data["resource_uri"]

        try:
            ct, created = model.objects.get_or_create(**court_data)
        except (IntegrityError, ValidationError):
            ct = model.objects.filter(pk=court_data["id"])[0]

        courts.append(ct)

        print(
            "View cloned court here:",
            reverse("court-detail", args=["v3", court_id]),
        )
    return courts


class Command(BaseCommand):
    help = (
        "Clone data from CourtListener.com into dev environment. It "
        "requires to set CL_API_TOKEN varible in the env file."
    )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.type = None
        self.ids = []
        self.download_cluster_files = False
        self.add_docket_entries = False

        self.s = requests.session()
        self.s.headers = {
            "Authorization": f"Token {os.environ.get('CL_API_TOKEN', '')}"
        }

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=VALID_TYPES,
            help="Object type to clone. Current choices are %s"
            % ", ".join(VALID_TYPES),
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
            "--add-docket-entries",
            action="store_true",
            default=False,
            help="Use this flag to clone docket entries when cloning "
            "clusters. It requires to have RECAP permissions or it will "
            "raise 403 error.",
        )

    def handle(self, *args, **options):
        self.type = options.get("type")
        self.ids = options.get("ids")
        self.download_cluster_files = options.get("download_cluster_files")
        self.add_docket_entries = options.get("add_docket_entries")

        if not settings.DEVELOPMENT:
            self.stdout.write("Command not enabled for production environment")

        match self.type:
            case "search.OpinionCluster":
                clone_opinion_cluster(
                    self.s,
                    self.ids,
                    self.download_cluster_files,
                    self.add_docket_entries,
                    self.type,
                )
            case "search.Docket":
                clone_docket(
                    self.s, self.ids, self.add_docket_entries, self.type
                )
            case "people_db.Person":
                clone_person(self.s, self.ids, self.type)
            case "search.Court":
                clone_court(self.s, self.ids, self.type)
            case _:
                self.stdout.write("Invalid type!")
