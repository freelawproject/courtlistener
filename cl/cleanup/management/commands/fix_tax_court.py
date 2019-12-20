# !/usr/bin/python
# -*- coding: utf-8 -*-

import re

from cl.citations import find_citations
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster, Docket, Citation


def get_tax_docket_numbers(opinion_text):
    """
    Parse opinon plain text for docket numbers.

    First we idenitify where the docket numbers are in the document.
    This is normally at the start of the document but can often follow
     a lengthy case details section.

    :param opinion_text: is the opinions plain_text
    :return docket_string: as string of docket numbers Ex. (18710-94, 12321-95)
    """
    parsed_text = None
    docket_no_re = r"Docket No.*Filed|Docket No.*(, [0-9]{4}.)"
    matches = re.finditer(docket_no_re, opinion_text)
    r = r"[0-9]{3,5}-[\w]{2,4}(\.)( [A-Z](\.))?"
    for matchNum, match in enumerate(matches, start=1):
        xst = opinion_text[match.start() :]
        second_matches = re.finditer(r, opinion_text[match.start() :])
        for match_num_2, second_match in enumerate(second_matches, start=1):
            parsed_text = xst[: second_match.end()]
            break
    # If we cant find the general area of docket number strings.  Give up.
    if parsed_text is None:
        return None

    docket_end_re = r"[0-9]{3,5}-[\w]{2,4}([A-Z])?(\,|\.)"

    matches = re.finditer(docket_end_re, parsed_text, re.MULTILINE)
    hits = []
    for matchNum, match in enumerate(matches, start=1):
        hits.append(match.group())
    docket_string = ", ".join(hits).replace(",,", ",").replace(".", "")
    return docket_string


def generate_citation(opinion_text, cluster_id):
    """
    Returns a dictionary representation of our
    Citation object.

    This data will only be returned if found, otherwise none is returned and
    no Citation object is added to the system.  It could be a failed parse
    or the data could simply not be available.

    :param opinion_text: The plain_text of our opinion from the scrape.
    :param cluster_id: The id of the associated Opinion_Cluster related
                        to this opinion
    :return: cite_dict => Returns dictionary of the citation data
    """
    for line_of_text in opinion_text.split("\n")[:250]:
        cites = find_citations.get_citations(line_of_text, html=False)
        if not cites:
            return

        for cite in cites:
            if "T.C." not in cite.reporter and "T. C." not in cite.reporter:
                continue

            if "T.C." == cite.reporter:
                cite_type = Citation.SPECIALTY
            elif "T.C. No." == cite.reporter:
                cite_type = Citation.SPECIALTY
            else:
                cite_type = Citation.NEUTRAL

            if not Citation.objects.filter(
                volume=cite.volume,
                reporter=cite.reporter,
                page=cite.page,
                cluster_id=cluster_id,
            ):
                cite.type = cite_type
                return cite


def update_tax_opinions():
    """
    This code identifies tax opinions without
    docket numbers or citations and attempts to parse them out
    and add the citation and docket numbers to the case.

    http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp is an identifier for
    bad scrapes in tax court.
    :return: None
    """
    logger.info("Start updating Tax Opinions")
    ocs = OpinionCluster.objects.filter(docket__court="tax").filter(
        docket__docket_number=None
    )

    # We had a number of failed scrapes and the bad_url helps identify them
    bad_url = "http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp"
    for oc in ocs:
        op_objs = oc.sub_opinions.all()
        for opinion in op_objs:
            if opinion.plain_text == "":
                # logger.info('Nothing to parse.')
                continue
            if opinion.download_url == bad_url:
                logger.info("Failed scrape, nothing to parse.")
                continue

            docket_numbers = get_tax_docket_numbers(opinion.plain_text)
            if docket_numbers:
                logger.info(
                    "Adding Docket Numbers: %s to %s"
                    % (docket_numbers, oc.docket.case_name)
                )
                oc.docket.docket_number = docket_numbers
                oc.docket.save()

            cite = generate_citation(opinion.plain_text, oc.id)

            if cite is None:
                logger.info(
                    "No cite found for opinion %s on cluster %s"
                    % (opinion.id, oc.id)
                )
                continue

            logger.info(
                "Citation saved %s %s %s"
                % (cite.volume, cite.reporter, cite.page)
            )

            Citation.objects.get_or_create(
                volume=cite.volume,
                reporter=cite.reporter,
                page=cite.page,
                type=cite.type,
                cluster_id=oc.id,
            )


class Command(VerboseCommand):
    help = (
        "Update scraped Tax Court opinions. "
        "Add citation and docket numbers."
    )

    def handle(self, *args, **options):
        update_tax_opinions()
