# !/usr/bin/python
# -*- coding: utf-8 -*-

import re

from cl.citations import find_citations
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster, Docket, Citation


def remove_en_em_dash(opinion_text):
    opinion_text = re.sub(u"–", "-", opinion_text)
    opinion_text = re.sub(u"—", "-", opinion_text)
    opinion_text = re.sub(u"–", "-", opinion_text)
    return opinion_text


def get_tax_docket_numbers(opinion_text):
    """
    Parse opinon plain text for docket numbers.

    First we idenitify where the docket numbers are in the document.
    This is normally at the start of the document but can often follow
     a lengthy case details section.

    :param opinion_text: is the opinions plain_text
    :return docket_string: as string of docket numbers Ex. (18710-94, 12321-95)
    """
    opinion_text = remove_en_em_dash(opinion_text)
    parsed_text = ""
    docket_no_re = r"Docket.? Nos?.? .*[0-9]{3,5}"
    matches = re.finditer(docket_no_re, opinion_text)

    for matchNum, match in enumerate(matches, start=1):
        parsed_text = opinion_text[match.start() :]
        break

    matches2 = re.finditer(r"([0-9]{3,5})(-|–)([0-9]{1,2})(\.)", parsed_text)
    for m2, match2 in enumerate(matches2, start=0):
        parsed_text = parsed_text[: match2.end()]
        break

    docket_end_re = r"[0-9]{3,5}(-|–)[\w]{2,4}([A-Z])?(\,|\.)"

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
            continue

        for cite in cites:
            if "T.C." not in cite.reporter and "T. C." not in cite.reporter:
                # If not the first cite - Skip
                return None

            if cite.reporter_index > 2:
                # If reporter not in first or second position bail
                return None

            alt_cite = line_of_text.replace(cite.reporter_found, "").strip()
            other_words = alt_cite.split(" ")

            if len([x for x in other_words if x != ""]) > 3:
                # If line has more than three components bail
                return None

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
            else:
                logger.info("Citation already in the system. Return None.")
                return None


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
                logger.info("No plain text to parse.")
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
                    "No cite to add for opinion %s on cluster %s"
                    % (opinion.id, oc.id)
                )
                continue

            logger.info(
                "Saving citation %s %s %s"
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
