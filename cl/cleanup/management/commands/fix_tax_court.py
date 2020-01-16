# !/usr/bin/python
# -*- coding: utf-8 -*-

import re
import argparse

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

    matches2 = re.finditer(
        r"[0-9]{3,5}(-|–)[\w]{2,4}([A-Z])?(\.)", parsed_text
    )
    for m2, match2 in enumerate(matches2, start=0):
        parsed_text = parsed_text[: match2.end()]
        break

    docket_end_re = r"[0-9]{3,5}(-|–)[\w]{2,4}([A-Z])?(\,|\.)"

    matches = re.finditer(docket_end_re, parsed_text, re.MULTILINE)
    hits = []
    for matchNum, match in enumerate(matches, start=1):
        hits.append(match.group())
    docket_string = ", ".join(hits).replace(",,", ",").replace(".", "")
    return docket_string.strip()


def find_tax_court_citation(opinion_text):
    """
    Returns a dictionary representation of our
    Citation object.

    Return the citation object or nothing.

    :param opinion_text: The plain_text of our opinion from the scrape.
    :return: citation object or None
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
                # If reporter not in first or second term in the line we skip.
                return None

            alt_cite = line_of_text.replace(cite.reporter_found, "").strip()
            other_words = alt_cite.split(" ")

            if len([x for x in other_words if x != ""]) > 3:
                # If line has more than three non reporter components skip.
                return None

            if "T.C." == cite.reporter:
                cite_type = Citation.SPECIALTY
            elif "T.C. No." == cite.reporter:
                cite_type = Citation.SPECIALTY
            else:
                cite_type = Citation.NEUTRAL

            cite.type = cite_type
            return cite


def update_tax_opinions(options):
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

            cite = find_tax_court_citation(opinion.plain_text)

            if cite is None:
                logger.info(
                    "No cite to add for opinion %s on cluster %s"
                    % (opinion.id, oc.id)
                )
                continue

            if Citation.objects.filter(
                volume=cite.volume,
                reporter=cite.reporter,
                page=cite.page,
                cluster_id=oc.id,
            ).exists():
                logger.info("Citation already in the system. Return None.")
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


def find_missing_or_incorrect_citations(options):
    """Iterate over tax cases to verify which citations are correctly parsed

    This code should pull back all the cases with plaintext tax courts to parse.
    Iterate over those cases extracting the citation if any

    :param options:
    :return:
    """

    ocs = OpinionCluster.objects.filter(docket__court="tax").exclude(
        sub_opinions__plain_text=""
    )
    logger.info("%s clusters found", ocs.count())

    clusters_with_errors = []

    for oc in ocs:
        logger.info("Analyzing cluster %s", oc.id)
        ops = oc.sub_opinions.all()
        assert ops.count() == 1
        for op in ops:
            # Only loop over the first opinion because these cases should only one have one
            # because they were extracted from the tax courts
            gen_cite = ""
            found_cite = find_tax_court_citation(op.plain_text)
            if found_cite is not None:
                gen_cite = found_cite.base_citation()
                logger.info("Found citation in plain text as %s", gen_cite)
            else:
                logger.info(
                    "No citation found in plain text for cluster: %s", oc.id
                )

        logger.info("Reviewing citations for cluster %s", oc.id)

        cites = oc.citations.all()

        cite_list = [str(cite) for cite in cites]
        cite_count = cites.count()

        if cite_count > 0:
            logger.info("Found %s citations in cluster %s", cite_count, oc.id)
            for cite in cite_list:
                if cite != gen_cite:
                    logger.info(
                        "Citation %s appears incorrect on cluster %s.",
                        cite,
                        oc.id,
                    )
                    clusters_with_errors.append(oc.id)
        else:
            if gen_cite != "":
                logger.info(
                    "Citation missing for cluster %s found as %s",
                    oc.id,
                    gen_cite,
                )
                clusters_with_errors.append(oc.id)
            else:
                logger.info("No citation in db or found in plain text")

    logger.info(
        "\n\nTo review:\nWrong or missing citations total = %s",
        len(clusters_with_errors),
    )
    for c in clusters_with_errors:
        logger.info("https://www.courtlistener.com/opinion/%s/x", c)


def find_missing_or_incorrect_docket_numbers(options):
    """Iterate over tax cases to verify which docket numbers are correct.

    :param options:
    :return: Nothing
    """
    ocs = OpinionCluster.objects.filter(docket__court="tax").exclude(
        sub_opinions__plain_text=""
    )

    logger.info("%s clusters found", ocs.count())

    for oc in ocs:
        logger.info("Analyzing cluster %s", oc.id)
        ops = oc.sub_opinions.all()
        assert ops.count() == 1
        for op in ops:
            logger.info(
                "Reference url: https://www.courtlistener.com/opinion/%s/x",
                oc.id,
            )
            # Only loop over the first opinion because these
            # cases should only one have one
            # because they were extracted from the tax courts
            dockets_in_db = oc.docket.docket_number.strip()
            found_dockets = get_tax_docket_numbers(op.plain_text)
            if found_dockets == dockets_in_db:
                if (
                    oc.docket.docket_number.strip() == ""
                    and dockets_in_db == ""
                ):
                    logger.info("No docket numbers found in db or text")
                else:
                    logger.info("Docket numbers appear correct")
                continue
            else:
                if dockets_in_db == "":
                    logger.info(
                        "Docket No(s). found for the first time: %s",
                        found_dockets,
                    )
                elif found_dockets == "":
                    logger.info(
                        "Dockets not found in text but Docket No(s). %s in db",
                        dockets_in_db,
                    )
                else:
                    logger.info(
                        "Dockets in db (%s) != (%s) docket parsed from text",
                        dockets_in_db,
                        found_dockets,
                    )


class Command(VerboseCommand):
    help = (
        "Update scraped Tax Court opinions. "
        "Add citation and docket numbers."
    )

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )
        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "update-tax-opinions": update_tax_opinions,
        "find-failures": find_missing_or_incorrect_citations,
        "find-docket-numbers": find_missing_or_incorrect_docket_numbers,
    }
