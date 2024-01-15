from cl.corpus_importer.bulk_utils import docket_pks_for_query
from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger

BULK_OUTPUT_DIRECTORY = "/sata/sample-data/mfb"
QUERY = "q=document_number:([50 TO 50000]) AND firm:(cravath OR wachtell OR skadden OR sullivan OR latham OR kirkland OR polk OR thacher OR gibson OR (paul AND weiss) OR weil OR sidley OR quinn OR cleary OR covington OR (jones AND day) OR (white AND case) OR debevoise OR (williams AND connolly) OR (ropes AND gray) OR (paul AND hastings) OR wilmer OR wilmerhale OR morrison OR boies OR milbank OR melveny OR hogan OR cooley OR proskauer OR akin OR (arnold AND porter) OR kaye OR baker OR (dla AND piper) OR orrick OR mayer OR (morgan AND lewis) OR goodwin OR sonsini OR spalding OR gates OR clifford OR munger OR winston OR shearman OR linklaters OR overy OR fried OR perkins OR dechert OR willkie OR cadwalader OR susman OR alston OR dentons OR traurig OR mcdermott OR freshfields OR cahill OR jenner OR (reed AND smith) OR vinson OR holland OR (norton AND rose) OR irell OR nixon OR crowell OR venable OR foley OR squire ro fish OR sheppard OR steptoe OR mcguire OR mcguirewoods OR arent OR fenwick OR locke OR schulte OR katten OR cave OR seyfarth OR pepper OR fox OR hughes OR duane OR haynes OR kramer OR tremaine OR troutman OR (blank AND rome) OR kilpatrick OR ballard OR drinker OR mintz OR kellog OR foley OR littler OR cozen) AND is_available:(true) AND dateFiled:[2010-01-01T00:00:00Z TO 2020-01-01T00:00:00Z]&type=r&order_by=score+desc"


def do_bulk_export(options):
    """Save selected dockets to disk

    This will serialize the items to disk using celery tasks and the IA
    serializer.
    """
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    for i, d_pk in enumerate(docket_pks_for_query(QUERY)):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break
        if i % 1000 == 0:
            logger.info("Doing item %s with pk %s", i, d_pk)
        throttle.maybe_wait()
        save_ia_docket_to_disk.apply_async(
            args=(d_pk, options["output_directory"]), queue=q
        )


class Command(VerboseCommand):
    help = "Export dockets and PDFs from our DB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--output-directory",
            type=str,
            help="Where the bulk data will be output to. Note that if Docker "
            "is used for Celery, this is a directory *inside* docker.",
            default=BULK_OUTPUT_DIRECTORY,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        do_bulk_export(options)
