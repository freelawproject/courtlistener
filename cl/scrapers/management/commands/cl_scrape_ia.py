# !/usr/bin/python
# -*- coding: utf-8 -*-

import re
import argparse
import requests
from internetarchive import get_files

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster, Docket, Citation
from cl.citations import find_citations

def find_docket_no_section(str):
    """
    This function attempts to find the docket No section that is often
    not on the first page.  This is then used to parse out the docket nos.

    :param str:
    :return:
    """
    regex = r"Docket No.*.Filed|Docket No.*.(, [0-9]{4}.)"
    matches = re.finditer(regex, str)
    r = r"[0-9]{3,5}-[0-9A-Za-z]{2,4}(\.)|([0-9]{3,5}-[0-9A-Za-z]{2,4} [A-Z](\.))"
    for matchNum, match in enumerate(matches, start=1):
        xst = str[match.start():]
        matches2 = re.finditer(r, str[match.start():])
        for matchNum, match in enumerate(matches2, start=1):
            return xst[:match.end()]

def get_docket_numbers(parsed_text):
    """
    Once the section has been parsed this regex grabs all of the docket nos.

    :param parsed_text:
    :return:
    """
    regex = r"[0-9]{3,5}-[0-9A-Za-z]{2,4}(\.)|([0-9]{3,5}-[0-9A-Za-z]{2,4} [A-Z](\.))"
    matches = re.finditer(regex, parsed_text, re.MULTILINE)
    hits = []
    for matchNum, match in enumerate(matches, start=1):
        hits.append(match.group())
    docket_string = ", ".join(hits).replace(",,", ",")
    return docket_string

def get_citation(str):
    """
    This function grabs the first citation looking string and then cleans out
    whitespace issues.  Then returns None (roughly 20/8500 times) or
    a dictionary of the citation.

    :param str:
    :return:
    """
    regex = r".{10}(T\.).*|.{10}(T\. C\.).{10}|(T\.).*|(T\. C\.).{10}"
    matches = re.finditer(regex, str)

    for matchNum, match in enumerate(matches, start=1):
        cite = match.group()
        cd = {}
        cite = cite.replace("T. C.", "T.C.").replace("Memo ", "Memo. ").replace("   ", " ").strip()
        if "T.C. Memo." in cite:
            cd['volume'] = cite.split("Memo.")[1].split("-")[0]
            cd['reporter'] = "T.C. Memo."
            cd['page'] = cite.split("Memo.")[1].split("-")[1]
            cd['type'] = 8
            return cd
        else:
            try:
                c = cite.split(" T.C. No. ")
                cd['volume'] = c[0].strip()
                cd['reporter'] = "T.C."
                cd['page'] = c[1].strip()
                cd['type'] = 4

                return cd
            except:
                return None
    return None

def update_tax_opinions(options):
    """
    This code should identifies tax opinions without docket numbers or citations
    and attempts to parse and add the citation and docket numbers to the case.

    http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp is an identifier for
    bad scrapes in tax court.
    :param options:
    :return:
    """
    op_clusters = OpinionCluster.objects.filter(docket__court="tax").\
                                filter(docket__docket_number=None)
    for oc in op_clusters:
        docket_number = None
        cites = None
        op_obj = Opinion.objects.get(cluster_id=oc.id)
        if op_obj.plain_text != "" and \
            op_obj.download_url != "http://www.ustaxcourt.gov/UstcInOp/asp/Todays.asp":
            for row in op_obj.plain_text.split("\n")[:250]:
                cites = find_citations.get_citations(row, html=False)
                try:
                    docket_section = find_docket_no_section(op_obj.plain_text)
                    docket_number = get_docket_numbers(docket_section).\
                        replace(".", "")
                except Exception as e:
                    pass

                if cites:
                    cite_dict = cites[0].__dict__

                    if "T.C." == cite_dict['reporter'] or \
                        "T.C. No." == cite_dict['reporter']:
                        cite_type = 4
                    else:
                        cite_type = 8

                    Citation.objects.create(**{
                        "volume" : cite_dict['volume'],
                        "reporter" : cite_dict['reporter'],
                        "page" : cite_dict['page'],
                        "type" : cite_type,
                        "cluster_id": oc.id
                    })

                    if docket_number:
                        docket = Docket.objects.get(id=oc.docket_id)
                        docket.docket_number = docket_number
                        docket.save()

                    logger.info("Saved Citation %s with docket no(s) %s" % (cite_dict, docket_number))
                    break

def add_cases_from_IA(options):
    """
    This function will collect cases from IA, determine if we have it - and
    then add missing cases to our DB.

    Provide the Vol(ume) and Court code information to extract from IA.
    Currently the code only provides the cite and URL.

    :param options:
    :return:
    """

    base = 'law.free.cap'

    volume = options['vol']
    reporter = options['court']

    ia_key = ".".join([base,
                       reporter.lower().replace(" ", "-").replace(".", ""),
                       volume])

    for item in get_files(ia_key):
        if "json.json" not in item.name and "json" in item.name:
            url = "https://archive.org/download/%s/%s" % (ia_key, item.name)
            cite = " ".join([volume, reporter, item.name.split(".")[0]])
            print cite, url



class Command(VerboseCommand):
    help = "Get all content from MAP LA Unlimited Civil Cases."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )

        # Action-specific parameters
        parser.add_argument(
            '--vol',
            help="A case that you want to download when using the add-case "
                 "action. For example, '19STCV25157;SS;CV'",
            default="1"
        )
        parser.add_argument(
            '--court',
            help="B.T.A. or T.C.",
            default="T.C."
        )
        parser.add_argument(
            '--skip-until',
            type=str,
            help="When using --directory-glob, skip processing until an item "
                 "at this location is encountered. Use a path comparable to "
                 "that passed to --directory-glob.",
        )


    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)

    VALID_ACTIONS = {
        'update-tax-cases': update_tax_opinions,
        'add-from-ia':add_cases_from_IA,
    }
