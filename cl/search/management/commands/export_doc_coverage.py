from datetime import datetime
from pathlib import Path
import time

import pandas as pd
from django.db.models import Count, Q
from elasticsearch_dsl import Search
from tqdm import tqdm

from cl.lib.command_utils import BaseCommand, logger
from cl.search.documents import DocketDocument
from cl.search.models import Docket


class Command(BaseCommand):
    help = """Export docket index with document coverage statistics for preparing a pretraining dataset.

    Two options here, a psql and elastic approach. I'm guessing the elastic version
    will be faster, but the psql has the advantage of pulling in stats on the number of
    rss entries which might be useful for sampling (I couldn't figure out description == '' in es!)

    Just pulls in minimal document level stats I thought might be useful for smapling a good set.
    We can merge in other header data from the bulk exports later.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-path",
            type=str,
            required=True,
            help="Path to save output as csv",
        )
        parser.add_argument(
            "--psql",
            action="store_true",
            help="Use postgres approch instead of elastic",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite the output file if it exists",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.0,
            help="Seconds to sleep betweeen batches",
        )
        parser.add_argument(
            "--max-es-buckets",
            type=float,
            default=500_000,
            help="Max number of cases per year to aggregate with ES approach",
        )

    def handle(self, *args, **options):
        out_path = Path(options["out_path"])
        if out_path.exists():
            if not options["overwrite"]:
                raise FileExistsError(
                    f"File already exists at {options['out_path']}. Use --overwrite to overwrite."
                )
            out_path.unlink()

        handler = self.handle_psql if options["psql"] else self.handle_es

        min_year = Docket.objects.earliest("date_filed").date_filed.year
        max_year = datetime.now().year
        years = list(range(min_year, max_year + 1))

        logger.info(f"Processing dockets from {min_year} to {max_year}...")
        for year in tqdm(years, desc="Processing by years"):
            start = datetime.now()
            data = handler(year, **options)
            if len(data):
                data = pd.DataFrame(data)
                if out_path.exists():
                    data.to_csv(out_path, mode="a", index=False, header=False)
                else:
                    data.to_csv(out_path, index=False)

            pct = (years.index(year) + 1) * 100 / len(years)
            elapsed = (datetime.now() - start).total_seconds()
            logger.info(
                f"Processed {year}. {pct:.2f}% done. Took {elapsed:.2f} seconds."
            )

            if options["sleep"] > 0 and pct < 100:
                logger.info(f"Sleeping for {options['sleep']} seconds...")
                time.sleep(options["sleep"])

        logger.info(f"Done! Saved to {out_path}")

    def handle_psql(self, year: int, **options: dict):
        # Prep filters
        is_document = Q(
            docket_entries__recap_documents__document_type__isnull=False
        )
        is_main_document = Q(docket_entries__recap_documents__document_type=1)
        is_available = Q(docket_entries__recap_documents__is_available=True)
        is_rss_document = Q(docket_entries__description="")

        # Run query
        dockets = Docket.objects.filter(
            date_filed__year=year, source__in=Docket.RECAP_SOURCES()
        )
        dockets = dockets.annotate(
            num_documents=Count(
                "docket_entries__recap_documents", filter=is_document
            ),
            num_main_documents=Count(
                "docket_entries__recap_documents", filter=is_main_document
            ),
            num_available=Count(
                "docket_entries__recap_documents", filter=is_available
            ),
            num_main_available=Count(
                "docket_entries__recap_documents",
                filter=is_main_document & is_available,
            ),
            num_main_rss_documents=Count(
                "docket_entries__recap_documents",
                filter=is_main_document & is_rss_document,
            ),
        )

        return dockets.values(
            "id",
            "court",
            "num_documents",
            "num_main_documents",
            "num_available",
            "num_main_available",
            "num_main_rss_documents",
        )

    def handle_es(self, year: int, **options: dict):
        s = Search(index=DocketDocument._index._name)

        # Prep filters
        is_main_document = {
            "bool": {"must_not": {"exists": {"field": "attachment_number"}}}
        }
        is_available = {"term": {"is_available": True}}
        is_main_available = {
            "bool": {"must": [is_main_document, is_available]}
        }

        # Run query
        s = s.query(
            "range",
            dateFiled={"gte": f"{year}-01-01", "lt": f"{year+1}-01-01"},
        )
        s = s.query("bool", filter={"exists": {"field": "document_type"}})

        s.aggs.bucket(
            "dockets", "terms", field="docket_id", size=options["max_es_buckets"]
        ).metric(
            "num_main_documents", "filter", filter=is_main_document,
        ).metric(
            "num_available", "filter", filter=is_available
        ).metric(
            "num_main_available", "filter", filter=is_main_available
        )

        s = s.extra(size=0, track_total_hits=False)
        response = s.execute()

        data = []
        for bucket in response.aggregations.dockets.buckets:
            total_docs = bucket.doc_count
            data.append(
                {
                    "id": bucket.key,
                    "num_documents": total_docs,
                    "num_main_documents": bucket.num_main_documents.doc_count,
                    "num_available": bucket.num_available.doc_count,
                    "num_main_available": bucket.num_main_available.doc_count,
                }
            )

        return data
