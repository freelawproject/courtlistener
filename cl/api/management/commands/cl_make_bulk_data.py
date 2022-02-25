import os
import shutil
from os.path import join
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from cl.api.tasks import make_bulk_data_and_swap_it_in
from cl.audio.api_serializers import AudioSerializer
from cl.audio.models import Audio
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.api_serializers import (
    EducationSerializer,
    PersonSerializer,
    PoliticalAffiliationSerializer,
    PositionSerializer,
    RetentionEventSerializer,
    SchoolSerializer,
)
from cl.people_db.models import (
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    RetentionEvent,
    School,
)
from cl.search.api_serializers import (
    CourtSerializer,
    DocketSerializer,
    OpinionClusterSerializer,
    OpinionSerializer,
)
from cl.search.models import Court, Docket, Opinion, OpinionCluster


class Command(VerboseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def handle(self, *args: List[str], **options: Dict[str, Any]):
        super(Command, self).handle(*args, **options)
        courts = Court.objects.all()

        kwargs_list = [
            {
                "obj_type_str": "clusters",
                "obj_class": OpinionCluster,
                "court_attr": "docket.court_id",
                "serializer": OpinionClusterSerializer,
            },
            {
                "obj_type_str": "opinions",
                "obj_class": Opinion,
                "court_attr": "cluster.docket.court_id",
                "serializer": OpinionSerializer,
            },
            {
                "obj_type_str": "dockets",
                "obj_class": Docket,
                "court_attr": "court_id",
                "serializer": DocketSerializer,
            },
            {
                "obj_type_str": "courts",
                "obj_class": Court,
                "court_attr": None,
                "serializer": CourtSerializer,
            },
            {
                "obj_type_str": "audio",
                "obj_class": Audio,
                "court_attr": "docket.court_id",
                "serializer": AudioSerializer,
            },
            {
                "obj_type_str": "people",
                "obj_class": Person,
                "court_attr": None,
                "serializer": PersonSerializer,
            },
            {
                "obj_type_str": "schools",
                "obj_class": School,
                "court_attr": None,
                "serializer": SchoolSerializer,
            },
            {
                "obj_type_str": "positions",
                "obj_class": Position,
                "court_attr": None,
                "serializer": PositionSerializer,
            },
            {
                "obj_type_str": "retention-events",
                "obj_class": RetentionEvent,
                "court_attr": None,
                "serializer": RetentionEventSerializer,
            },
            {
                "obj_type_str": "educations",
                "obj_class": Education,
                "court_attr": None,
                "serializer": EducationSerializer,
            },
            {
                "obj_type_str": "politicial-affiliations",
                "obj_class": PoliticalAffiliation,
                "court_attr": None,
                "serializer": PoliticalAffiliationSerializer,
            },
        ]

        logger.info(
            f"Starting bulk file creation with {len(kwargs_list)} celery "
            f"tasks..."
        )
        for kwargs in kwargs_list:
            make_bulk_data_and_swap_it_in(
                courts, settings.BULK_DATA_DIR, kwargs
            )

        # Make the citation and parenthetical bulk data
        csv_dump_infos = [
            {
                "obj_type_str": "citations",
                "table": "search_opinionscited",
                "columns": "citing_opinion_id, cited_opinion_id, depth",
            },
            {
                "obj_type_str": "parentheticals",
                "table": "search_parenthetical",
                "columns": "describing_opinion_id, described_opinion_id, text, score",
            },
        ]

        for csv_dump_info in csv_dump_infos:
            obj_type_str = csv_dump_info["obj_type_str"]
            logger.info(f" - Creating bulk data CSV for {obj_type_str}...")
            tmp_destination = join(settings.BULK_DATA_DIR, "tmp", obj_type_str)
            final_destination = join(settings.BULK_DATA_DIR, obj_type_str)
            self.make_citation_data(tmp_destination, csv_dump_info)
            logger.info(f"   - Swapping in the new {obj_type_str} archives...")

            Path(final_destination).mkdir(parents=True, exist_ok=True)
            shutil.move(
                join(tmp_destination, "all.csv.gz"),
                join(final_destination, "all.csv.gz"),
            )

        logger.info("Done.\n")

    @staticmethod
    def make_citation_data(
        tmp_destination: str, csv_dump_info: Dict[str, str]
    ) -> None:
        """Dump the DB for citations and parentheticals to a CSV.

        Generating a JSON file for every citation or parenthetical is not
        good for anybody. Instead of doing that, we dump our citation and
        parenthetical tables with a shell command. This provides people with
        compact and reasonable data they can import.

        :param tmp_destination: Where to create the CSV.
        :param csv_dump_info: A dict containing info about how to select the
        correct columns from the correct table in the DB.
        """
        Path(tmp_destination).mkdir(parents=True, exist_ok=True)
        logger.info(
            f"   - Copying the {csv_dump_info['obj_type_str']} table to disk..."
        )

        # This command calls the psql COPY command and requests that it dump
        # the table to disk as a compressed CSV.
        default_db = settings.DATABASES["default"]
        os.system(
            """PGPASSWORD="{password}" psql -c "COPY \\"{table}}\\" ({columns}) to stdout DELIMITER ',' CSV HEADER" --host {host} --dbname {database} --username {username} | gzip > {destination}""".format(
                password=default_db["PASSWORD"],
                table=csv_dump_info["table"],
                columns=csv_dump_info["columns"],
                host=default_db["HOST"],
                database=default_db["NAME"],
                username=default_db["USER"],
                destination=join(tmp_destination, "all.csv.gz"),
            )
        )
        logger.info("   - Table created successfully.")
