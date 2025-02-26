import time
from datetime import datetime
from pathlib import Path

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
        max_date = datetime.now()

        date_ranges = []
        current = datetime(min_year, 1, 1)
        while current <= max_date:
            date_ranges.append((current.year, current.month))
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

        logger.info(
            f"Processing dockets from {min_year}-01 to {max_date.year}-{max_date.month}..."
        )
        for year, month in tqdm(date_ranges, desc="Processing by year-month"):
            start = datetime.now()
            data = handler(year, month, options)
            if len(data):
                data = pd.DataFrame(data)
                if out_path.exists():
                    data.to_csv(out_path, mode="a", index=False, header=False)
                else:
                    data.to_csv(out_path, index=False)

            pct = (
                (date_ranges.index((year, month)) + 1) * 100 / len(date_ranges)
            )
            elapsed = (datetime.now() - start).total_seconds()
            logger.info(
                f"Processed {year}-{month:02d}. {pct:.2f}% done. Took {elapsed:.2f} seconds."
            )

            if options["sleep"] > 0 and pct < 100:
                logger.info(f"Sleeping for {options['sleep']} seconds...")
                time.sleep(options["sleep"])

        logger.info(f"Done! Saved to {out_path}")

    def handle_psql(self, year: int, month: int, options: dict):
        # Prep filters
        is_document = Q(
            docket_entries__recap_documents__document_type__isnull=False
        )
        is_main_document = Q(docket_entries__recap_documents__document_type=1)
        is_available = Q(docket_entries__recap_documents__is_available=True)
        is_rss_document = Q(docket_entries__description="")

        # Run query
        dockets = Docket.objects.filter(
            date_filed__year=year,
            date_filed__month=month,
            source__in=Docket.RECAP_SOURCES(),
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

    def handle_es(self, year: int, month: int, options: dict):

        def get_composite_query(after=None):
            next_month = month + 1
            next_year = year
            if next_month > 12:
                next_month = 1
                next_year = year + 1

            query = {
                "size": 0,
                "track_total_hits": False,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {"docket_child": "recap_document"},
                            },
                            {
                                "range": {
                                    "dateFiled": {
                                        "gte": f"{year}-{month:02d}-01",
                                        "lt": f"{next_year}-{next_month:02d}-01",
                                    }
                                }
                            },
                        ]
                    }
                },
                "aggs": {
                    "dockets": {
                        "composite": {
                            "size": 10000,
                            "sources": [
                                {
                                    "docket_id": {
                                        "terms": {"field": "docket_id"}
                                    }
                                }
                            ],
                        },
                        "aggs": {
                            "num_main_documents": {
                                "filter": {
                                    "bool": {
                                        "must_not": {
                                            "exists": {
                                                "field": "attachment_number"
                                            }
                                        }
                                    }
                                }
                            },
                            "num_available": {
                                "filter": {"term": {"is_available": True}}
                            },
                            "num_main_available": {
                                "filter": {
                                    "bool": {
                                        "must": [
                                            {
                                                "bool": {
                                                    "must_not": {
                                                        "exists": {
                                                            "field": "attachment_number"
                                                        }
                                                    }
                                                }
                                            },
                                            {"term": {"is_available": True}},
                                        ]
                                    }
                                }
                            },
                        },
                    }
                },
            }

            if after:
                query["aggs"]["dockets"]["composite"]["after"] = after
            return query

        after = None
        data = []

        while True:
            query = get_composite_query(after)

            s = Search(index=DocketDocument._index._name)
            s = s.update_from_dict(query)
            response = s.execute()
            buckets = response["aggregations"]["dockets"]["buckets"]

            if not buckets:
                break

            for bucket in buckets:
                data.append(
                    {
                        "id": bucket.key.docket_id,
                        "num_documents": bucket.doc_count,
                        "num_main_documents": bucket.num_main_documents.doc_count,
                        "num_available": bucket.num_available.doc_count,
                        "num_main_available": bucket.num_main_available.doc_count,
                    }
                )

            after = response.aggregations.dockets.after_key

            if not after:
                break
            logger.info(
                f"Adding data for {year}-{month:02d} ({len(data)} total so far)"
            )

            if options["sleep"] > 0:
                time.sleep(options["sleep"])
        return data
