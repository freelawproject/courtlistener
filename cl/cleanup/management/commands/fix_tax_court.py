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
    regex = r"Docket No.*.Filed|Docket No.*.(, [0-9]{4}.)"
    matches = re.finditer(regex, opinion_text)
    r = r"[0-9]{3,5}-[\w]{2,4}(\.)( [A-Z](\.))?"
    for matchNum, match in enumerate(matches, start=1):
        xst = opinion_text[match.start():]
        second_matches = re.finditer(r, opinion_text[match.start():])
        for match_num_2, second_match in enumerate(second_matches, start=1):
            parsed_text = xst[:second_match.end()]
            break
    # If we cant find the general area of docket number strings.  Give up.
    if parsed_text is None:
        return None

    regex = r"[0-9]{3,5}-[\w]{2,4}([A-Z])?(\,|\.)"

    matches = re.finditer(regex, parsed_text, re.MULTILINE)
    hits = []
    for matchNum, match in enumerate(matches, start=1):
        hits.append(match.group())
    docket_string = ', '.join(hits).replace(',,', ',').replace('.', '')
    return docket_string


def generate_citation(opinion_text, cluster_id):
    """
    Generate_Citation returns a dictionary representation of our
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
            cite_dict = cite.__dict__
            if "T.C." not in cite_dict['reporter']:
                continue

            if "T.C." == cite_dict['reporter']:
                cite_type = 4
            elif "T.C. No." == cite_dict['reporter']:
                cite_type = 4
            else:
                cite_type = 8

            if not Citation.objects.filter(volume=cite_dict['volume'],
                                           reporter=cite_dict[
                                               'reporter'],
                                           page=cite_dict['page'],
                                           cluster_id=cluster_id):
                cite_dict['cite_type'] = cite_type
                return cite_dict


def update_tax_opinions():
    """
    This code should identifies tax opinions without
    docket numbers or citations and attempts to parse them out
    and add the citation and docket numbers to the case.

    http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp is an identifier for
    bad scrapes in tax court.
    :return: None
    """
    logger.info("Start updating Tax Opinions")
    op_clusters = OpinionCluster.objects.filter(docket__court="tax"). \
        filter(docket__docket_number=None)

    # We had a number of failed scrapes and the bad_url helps identify them
    bad_url = "http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp"
    for oc in op_clusters:
        op_obj = Opinion.objects.filter(cluster_id=oc.id)
        for opinion in op_obj:
            if opinion.plain_text == "":
                logger.info('Nothing to parse.')
                continue
            if opinion.download_url == bad_url:
                logger.info("Failed scrape, nothing to parse.")
                continue
            docket_numbers = get_tax_docket_numbers(opinion.plain_text)

            if docket_numbers:
                docket = Docket.objects.get(id=oc.docket_id)
                docket.docket_number = docket_numbers
                docket.save()
                logger.info("Adding Docket Numbers: %s to %s" %
                            (docket_numbers, docket.case_name))

            cite_dict = generate_citation(opinion.plain_text, oc.id)

            if cite_dict is None:
                continue

            Citation.objects.create(**{
                "volume": cite_dict['volume'],
                "reporter": cite_dict['reporter'],
                "page": cite_dict['page'],
                "type": cite_dict['cite_type'],
                "cluster_id": oc.id
            })

            logger.info("Citation saved %s %s %s" % (cite_dict['volume'],
                                                     cite_dict['reporter'],
                                                     cite_dict['page']
                                                     )
                        )


class Command(VerboseCommand):
    help = 'Update scraped Tax Court opinions. ' \
           'Add citation and docket numbers.'

    def handle(self, *args, **options):
        update_tax_opinions()
