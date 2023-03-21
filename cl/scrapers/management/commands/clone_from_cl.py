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

import os

import requests
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.dateparse import parse_date
from requests import Session

from cl.search.models import Citation, Opinion
from cl.search.tasks import add_items_to_solr

VALID_TYPES = (
    "search.OpinionCluster",
    "search.Docket",
    "people_db.Person",
    "search.Court",
)

domain = "https://www.courtlistener.com"


def get_id_from_url(api_url: str) -> str:
    """Get the PK from an API url"""
    return api_url.split("/")[-2]


def clone_opinion_cluster(
    session: Session, cluster_ids: list, object_type="search.OpinionCluster"
):
    """
    Download opinion cluster data from courtlistener.com and add it to
    local environment
    :param session: a Requests session
    :param cluster_ids: a list of opinion cluster ids
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
        cluster_datum = session.get(cluster_url, timeout=60).json()
        docket_id = get_id_from_url(cluster_datum["docket"])
        docket = clone_docket(session, [docket_id])[0]
        citation_data = cluster_datum["citations"]
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

        prepared_opinion_data = []
        added_opinions_ids = []

        for op in sub_opinions_data:
            # Get opinion from api
            op_data = session.get(op, timeout=60).json()
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
            # Append new data
            prepared_opinion_data.append(op_data)

        with transaction.atomic():
            # Create opinion cluster
            opinion_cluster = model.objects.create(**cluster_datum)

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
    session: Session, docket_ids: list, object_type="search.Docket"
):
    """
    Download docket data from courtlistener.com and add it to local
    environment
    :param session: a Requests session
    :param docket_ids: a list of docket ids
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
            continue
        except model.DoesNotExist:
            pass

        # Create new Docket
        docket_path = reverse(
            "docket-detail",
            kwargs={"version": "v3", "pk": docket_id},
        )
        docket_url = f"{domain}{docket_path}"
        docket_data = session.get(docket_url, timeout=60).json()

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


def clone_person(
    session: Session, people_ids: list, object_type="people_db.Person"
):
    """
    Download person data from courtlistener.com and add it to local
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
        person_data = session.get(person_url, timeout=60).json()
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
    """
    Download court data from courtlistener.com and add it to local
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
        court_data = session.get(court_url, timeout=60).json()
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
    help = "Clone data from CourtListener.com into dev environment"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
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

    def handle(self, *args, **options):
        self.type = options.get("type")
        self.ids = options.get("ids")

        if not settings.DEVELOPMENT:
            self.stdout.write("Command not enabled for production environment")

        match self.type:
            case "search.OpinionCluster":
                clone_opinion_cluster(self.s, self.ids, self.type)
            case "search.Docket":
                clone_docket(self.s, self.ids, self.type)
            case "people_db.Person":
                clone_person(self.s, self.ids, self.type)
            case "search.Court":
                clone_court(self.s, self.ids, self.type)
            case _:
                self.stdout.write("Invalid type!")
