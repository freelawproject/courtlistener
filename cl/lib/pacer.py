import logging
import os
from datetime import date

from dateutil import parser
from dateutil.tz import gettz
from django.db import IntegrityError
from django.db.models import Q
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from lxml import etree

from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.lib.import_lib import find_person
from cl.lib.recap_utils import (
    get_docketxml_url_from_path, get_ia_document_url_from_path,
    get_local_document_url_from_path,
)
from cl.scrapers.tasks import get_page_count
from cl.search.models import Court, Docket, RECAPDocument, DocketEntry

logger = logging.getLogger(__name__)


pacer_to_cl_ids = {
    # Maps PACER ids to their CL equivalents
    'azb': 'arb',         # Arizona Bankruptcy Court
    'cofc': 'uscfc',      # Court of Federal Claims
    'nysb-mega': 'nysb',  # Remove the mega thing
}
# Reverse dict of pacer_to_cl_ids
cl_to_pacer_ids = {v: k for k, v in pacer_to_cl_ids.items()}


class ParsingException(Exception):
    pass


class PacerXMLParser(object):
    """A class to parse a PACER XML file"""

    cnt = CaseNameTweaker()

    def __init__(self, path):
        logger.info("Initializing parser for %s" % path)
        # High-level attributes
        self.path = path
        self.xml = self.get_xml_contents()
        self.case_details = self.get_case_details()
        self.document_list = self.get_document_list()
        self.document_count = self.get_document_count()

        # Docket attributes
        self.court = self.get_court()
        self.docket_number = self.get_str_from_node(
            self.case_details, 'docket_num')
        self.pacer_case_id = self.get_str_from_node(
            self.case_details, 'pacer_case_num')
        self.date_filed = self.get_datetime_from_node(
            self.case_details, 'date_case_filed', cast_to_date=True)
        self.date_terminated = self.get_datetime_from_node(
            self.case_details, 'date_case_terminated', cast_to_date=True)
        self.date_last_filing = self.get_datetime_from_node(
            self.case_details, 'date_last_filing', cast_to_date=True)
        self.case_name = harmonize(self.get_str_from_node(
            self.case_details, 'case_name'))
        self.case_name_short = self.cnt.make_case_name_short(self.case_name)
        self.cause = self.get_str_from_node(
            self.case_details, 'case_cause')
        self.nature_of_suit = self.get_str_from_node(
            self.case_details, 'nature_of_suit')
        self.jury_demand = self.get_str_from_node(
            self.case_details, 'jury_demand')
        self.jurisdiction_type = self.get_str_from_node(
            self.case_details, 'jurisdiction')
        self.assigned_to, self.assigned_to_str = self.get_judges('assigned_to')
        self.referred_to, self.referred_to_str = self.get_judges('referred_to')
        self.blocked, self.date_blocked = self.set_blocked_fields()

        # Non-parsed fields
        self.filepath_local = os.path.join('recap', self.path)
        self.filepath_ia = get_docketxml_url_from_path(self.path)

    def save(self, debug):
        """Save the item to the database, updating any existing items.

        Returns None if an error occurs.
        """
        required_fields = ['case_name', 'date_filed']
        for field in required_fields:
            if not getattr(self, field):
                print "  Missing required field: %s" % field
                return None

        try:
            d = Docket.objects.get(
                Q(pacer_case_id=self.pacer_case_id) |
                Q(docket_number=self.docket_number),
                court=self.court,
            )
            # Add RECAP as a source if it's not already.
            if d.source in [Docket.DEFAULT, Docket.SCRAPER]:
                d.source = Docket.RECAP_AND_SCRAPER
            elif d.source == Docket.COLUMBIA:
                d.source = Docket.COLUMBIA_AND_RECAP
            elif d.source == Docket.COLUMBIA_AND_SCRAPER:
                d.source = Docket.COLUMBIA_AND_RECAP_AND_SCRAPER
        except Docket.DoesNotExist:
            d = Docket(source=Docket.RECAP)
        except Docket.MultipleObjectsReturned:
            print "  Got multiple results while attempting save."
            return None

        for attr, v in self.__dict__.items():
            setattr(d, attr, v)

        if not debug:
            d.save()
            print "  Saved as Docket %s: https://www.courtlistener.com%s" % (
                d.pk,
                d.get_absolute_url()
            )
        return d

    def get_xml_contents(self):
        """Extract the XML from the file on disk and return it as an lxml
        tree
        """
        xml_parser = etree.XMLParser(recover=True)
        tree = etree.parse(self.path, xml_parser)

        return tree

    def get_case_details(self):
        """Most of the details are in the case_details node, so set it aside
        for faster parsing.
        """
        return self.xml.xpath('//case_details')[0]

    def get_document_list(self):
        """Get the XML nodes for the documents"""
        return self.xml.xpath('//document_list/document')

    def get_document_count(self):
        """Get the number of documents associated with this docket."""
        return len(self.document_list)

    def make_documents(self, docket, debug):
        """Parse through the document nodes, making good objects.

        For every node, create a line item on the Docket (a DocketEntry), and
        create 1..n additional RECAPDocuments (attachments or regular documents)
        that are associated with that DocketEntry.

        Returns None if an error occurs.
        """
        recap_docs = []
        for doc_node in self.document_list:
            # Make a DocketEntry object
            entry_number = doc_node.xpath('@doc_num')[0]
            attachment_number = int(doc_node.xpath('@attachment_num')[0])
            print "Working on document %s, attachment %s" % (entry_number,
                                                             attachment_number)

            if attachment_number == 0:
                document_type = RECAPDocument.PACER_DOCUMENT
            else:
                document_type = RECAPDocument.ATTACHMENT

            try:
                docket_entry = DocketEntry.objects.get(
                    docket=docket,
                    entry_number=entry_number,
                )
            except DocketEntry.DoesNotExist:
                if document_type == RECAPDocument.PACER_DOCUMENT:
                    docket_entry = DocketEntry(
                        docket=docket,
                        entry_number=entry_number,
                    )
                else:
                    logger.error(
                        "Tried to create attachment without a DocketEntry "
                        "object to associate it with."
                    )
                    continue

            if document_type == RECAPDocument.PACER_DOCUMENT:
                date_filed = (
                    self.get_datetime_from_node(doc_node, 'date_filed',
                                                cast_to_date=True) or
                    docket_entry.date_filed
                )
                docket_entry.date_filed = date_filed
                docket_entry.description = (
                    self.get_str_from_node(doc_node, 'long_desc') or
                    docket_entry.description
                )
                try:
                    if not debug:
                        docket_entry.save()
                except (IntegrityError,
                        DocketEntry.MultipleObjectsReturned) as e:
                    logger.error(
                        "Unable to create docket entry for docket #%s, on "
                        "entry: %s." % (docket, entry_number)
                    )
                    continue

            recap_doc = self.make_recap_document(
                doc_node,
                docket_entry,
                entry_number,
                attachment_number,
                document_type,
                debug,
            )
            if recap_doc is not None:
                recap_docs.append(recap_doc)

        return [item.pk for item in recap_docs]

    def make_recap_document(self, doc_node, docket_entry, entry_number,
                            attachment_number, document_type, debug):
        """Make a PACER document."""
        pacer_document_id = self.get_str_from_node(
            doc_node, 'pacer_doc_id')
        try:
            d = RECAPDocument.objects.get(
                docket_entry=docket_entry,
                document_number=entry_number,
                # Use the attachment number if it is not 0, else use None.
                attachment_number=attachment_number or None,
            )
        except RECAPDocument.DoesNotExist:
            d = RECAPDocument(
                docket_entry=docket_entry,
                pacer_doc_id=pacer_document_id,
            )
        else:
            d.pacer_doc_id = pacer_document_id or d.pacer_doc_id

        d.date_upload = self.get_datetime_from_node(doc_node, 'upload_date')
        d.document_type = document_type or d.document_type
        d.document_number = entry_number

        # If we can't parse the availability node (it returns None), default it
        # to False.
        availability = self.get_bool_from_node(doc_node, 'available')
        d.is_available = False if availability is None else availability
        d.sha1 = self.get_str_from_node(doc_node, 'sha1')
        d.description = (self.get_str_from_node(doc_node, 'short_desc') or
                         d.description)
        if d.is_available:
            d.filepath_ia = get_ia_document_url_from_path(
                self.path, entry_number, attachment_number)
            d.filepath_local = os.path.join(
                'recap',
                get_local_document_url_from_path(self.path, entry_number,
                                                 attachment_number),
            )
            if d.page_count is None:
                extension = d.filepath_local.path.split('.')[-1]
                d.page_count = get_page_count(d.filepath_local.path, extension)
        if document_type == RECAPDocument.ATTACHMENT:
            d.attachment_number = attachment_number
        if not debug:
            try:
                d.save(do_extraction=False, index=False)
            except IntegrityError as e:
                # This happens when a pacer_doc_id has been wrongly set as
                # the document_number, see for example, document 19 and
                # document 00405193374 here: https://ia802300.us.archive.org/23/items/gov.uscourts.ca4.14-1872/gov.uscourts.ca4.14-1872.docket.xml
                logger.error("Unable to create RECAPDocument for document #%s, "
                             "attachment #%s on entry: %s due to "
                             "IntegrityError." % (d.document_number,
                                                  d.attachment_number,
                                                  d.docket_entry))
                return None
        return d

    def get_court(self):
        """Extract the court from the XML and return it as a Court object"""
        court_str = self.case_details.xpath('court/text()')[0].strip()
        try:
            c = Court.objects.get(pk=pacer_to_cl_ids.get(court_str, court_str))
        except Court.DoesNotExist:
            raise ParsingException("Unable to identify court: %s" % court_str)
        else:
            return c

    @staticmethod
    def get_bool_from_node(node, path):
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
            n = int(s)
        except IndexError:
            print "  Couldn't get bool from path: %s" % path
            return None
        except ValueError:
            print ("  Couldn't convert text '%s' to int when making boolean "
                   "for path: %s" % (s, path))
            return None
        else:
            return bool(n)

    @staticmethod
    def get_str_from_node(node, path):
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
        except IndexError:
            print "  Couldn't get string from path: %s" % path
            return ''  # Return an empty string. Don't return None.
        else:
            return s

    def get_int_from_details(self, node):
        s = self.case_details.xpath('%s/text()' % node)[0].strip()
        try:
            return int(s)
        except ValueError:
            # Can't parse string to int
            print "  Couldn't get int for node %s" % node
            raise ParsingException("Cannot extract int for node %s" % node)

    @staticmethod
    def get_datetime_from_node(node, path, cast_to_date=False):
        """Parse a datetime from the XML located at node."""
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
        except IndexError:
            print "  Couldn't get date from path: %s" % path
            return None
        else:
            try:
                d = parser.parse(s)
            except ValueError:
                print "  Couldn't parse date: %s" % s
                return None
            else:
                d = d.replace(tzinfo=d.tzinfo or gettz('UTC'))  # Set it to UTC.
                if cast_to_date is True:
                    return d.date()
                return d

    def get_judges(self, node):
        """Parse out the judge string and then look it up in the DB"""
        try:
            s = self.case_details.xpath('%s/text()' % node)[0].strip()
        except IndexError:
            print "  Couldn't get judge for node: %s" % node
            return None, ''
        else:
            judge_names = find_judge_names(s)
            judges = []
            for judge_name in judge_names:
                judges.append(find_person(judge_name, self.court.pk,
                                          case_date=self.date_filed))
            judges = [c for c in judges if c is not None]
            if len(judges) == 0:
                print "  No judges found after lookup."
                logger.info("No judge for: %s" % (
                    (s, self.court.pk, self.date_filed),
                ))
                return None, s
            elif len(judges) == 1:
                return judges[0], s
            elif len(judges) > 1:
                print "  Too many judges found: %s" % len(judges)
                return None, s

    def set_blocked_fields(self):
        """Set the blocked status for the Docket.

        Dockets are public (blocked is False) when:

                                   Is Bankr. Court
                                +---------+--------+
                                |   YES   |   NO   |
                +---------------+---------+--------+
         Size   | > 500 items   |    X    |    X   |
          of    +---------------+---------+--------+
        Docket  | <= 500 items  |         |    X   |
                +---------------+---------+--------+

        """
        bankruptcy_privacy_threshold = 500
        small_case = self.document_count <= bankruptcy_privacy_threshold
        if all([small_case, self.court.is_bankruptcy]):
            return True, date.today()
        return False, None
