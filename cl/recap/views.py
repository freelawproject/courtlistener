from rest_framework.viewsets import ModelViewSet

from cl.api.utils import RECAPUploaders, LoggingMixin
from cl.recap.api_serializers import ProcessingQueueSerializer
from cl.recap.models import ProcessingQueue


class PacerProcessingQueueViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (RECAPUploaders,)
    queryset = ProcessingQueue.objects.all()
    serializer_class = ProcessingQueueSerializer

    def perform_create(self, serializer):
        serializer.save(uploader=self.request.user)


def pacer_docket_upload(request):
    """
    This will accept a RECAP docket and will save it to a database table.
     
    The ID from the saved object will be passed to a celery task, which will 
    pop the row from the database table, process it, and mark it as complete.
     
    A background script (if we want) can come through and clean up old items
    that were processed long ago. 
    
    
    :param request: 
    :return: 
    """
    pass


def pacer_pdf_upload(request):
    pass


def pacer_doc1_upload(request):
    pass

#
# def upload(request):
#     """ Public upload view for all incoming data. """
#
#     if request.method != "POST":
#         message = "upload: Not a POST request."
#         logging.error(message)
#         return HttpResponse(message)
#
#     try:
#         if not request.FILES:
#             message = "upload: No request.FILES attribute."
#             logging.error(message)
#             return HttpResponse(message)
#     except IOError:
#         # Not something we can fix I don't think.  Client fails to send data.
#         message = "Client read error (Timeout?)"
#         logging.warning("upload: %s" % message)
#         return HttpResponse(message)
#     except SystemError:
#         message = "Could not parse POST arguments."
#         logging.warning("uploads: %s" % message)
#         return HttpResponse(message)
#
#     try:
#         data = request.FILES["data"]
#     except KeyError:
#         try:
#             # TK: Only used in testing - get rid of me
#             data = request.FILES["data_file"]
#         except KeyError:
#             message = "upload: No FILES 'data' attribute."
#             logging.error(message)
#             return HttpResponse(message)
#
#     try:
#         court = request.POST["court"]
#     except KeyError:
#         message = "upload: No POST 'court' attribute."
#         logging.error(message)
#         return HttpResponse(message)
#     else:
#         court = court.strip()
#
#     if request.POST.get("casenum"):
#         casenum = request.POST["casenum"].strip()
#         casenum_re = re.compile(r'\d+(-\d+)?')
#         if not casenum_re.match(casenum) or ":" in casenum:
#             message = "upload: 'casenum' invalid: %s" % request.POST["casenum"]
#             logging.error(message)
#             return HttpResponse(message)
#     else:
#         casenum = None
#
#     try:
#         mimetype = request.POST["mimetype"].strip()
#     except KeyError:
#         message = "upload: No POST 'mimetype' attribute."
#         logging.error(message)
#         return HttpResponse(message)
#
#     try:
#         url = request.POST["url"].strip()
#     except KeyError:
#         url = None
#
#     message = UploadHandler.handle_upload(data, court, casenum, mimetype, url)
#
#     return HttpResponse(message)
#
#
# def query(request):
#     """  Query the database to check which PDF documents we have.
#
#          The json input is {"court": <court>,
#                             "urls": <list of PACER doc1 urls>}
#
#          The json output is a set of mappings:
#                            {<pacer url>: { "filename": <public url>,
#                                            "timestamp": <last time seen> },
#                             <pacer url>: ... }
#     """
#     response = {}
#
#     if request.method != "POST":
#         message = "query: Not a POST request."
#         logging.error(message)
#         return HttpResponse(message)
#
#     try:
#         jsonin = simplejson.loads(request.POST["json"])
#     except KeyError:
#         message = "query: no 'json' POST argument"
#         logging.warning(message)
#         return HttpResponse(message)
#     except ValueError:
#         message = "query: malformed 'json' POST argument"
#         logging.warning(message)
#         return HttpResponse(message)
#     except IOError:
#         # Not something we can fix I don't think.  Client fails to send data.
#         message = "query: Client read error (Timeout?)"
#         logging.warning(message)
#         return HttpResponse(message)
#
#     try:
#         court = jsonin["court"].strip()
#     except KeyError:
#         message = "query: missing json 'court' argument."
#         logging.warning(message)
#         return HttpResponse(message)
#
#     try:
#         urls = jsonin["urls"]
#     except KeyError:
#         message = "query: missing json 'urls' argument."
#         logging.warning(message)
#         return HttpResponse(message)
#
#     for url in urls:
#         # detect show_doc style document links
#         sdre = re.search("show_doc\.pl\?(.*)", url)
#
#         if sdre:
#             argsstring = sdre.group(1)
#             args = argsstring.split("&")
#             argsdict = {}
#
#             for arg in args:
#                 (key, val) = arg.split("=")
#                 argsdict[key] = val
#
#             # maybe need to add some checks for whether
#             # these vars exist in argsdict
#             query = Document.objects.filter(court=court) \
#                 .filter(docnum=argsdict["doc_num"]) \
#                 .filter(casenum=argsdict["caseid"]) \
#                 .filter(dm_id=int(argsdict["dm_id"])) \
#                 .filter(available=1)
#
#         else:
#             # otherwise, assume it's a normal doc1 style url
#             docid = UploadHandler.docid_from_url_name(url)
#             query = Document.objects.filter(docid=docid) \
#                 .filter(available=1)
#
#         if query:
#             query = query[0]
#             real_casenum = query.casenum
#
#             response[url] = {
#                 "filename": IACommon.get_pdf_url(court,
#                                                  real_casenum,
#                                                  query.docnum,
#                                                  query.subdocnum),
#                 "timestamp": query.lastdate.strftime("%m/%d/%y")}
#
#             if query.subdocnum == 0:
#                 subquery = Document.objects.filter(
#                     court=court,
#                     casenum=query.casenum,
#                     docnum=query.docnum,
#                     available=1).exclude(subdocnum=0)
#
#                 if len(subquery) > 0:
#                     response[url]["subDocuments"] = {}
#
#                     for subDoc in subquery:
#                         real_sub_casenum = subDoc.casenum
#                         response[url]["subDocuments"][subDoc.subdocnum] = {
#                             "filename": IACommon.get_pdf_url(court,
#                                                              real_sub_casenum,
#                                                              subDoc.docnum,
#                                                              subDoc.subdocnum),
#                             "timestamp": subDoc.lastdate.strftime("%m/%d/%y")}
#
#     jsonout = simplejson.dumps(response)
#
#     return HttpResponse(jsonout, mimetype="application/json")
#
#
# def query_cases(request):
#     """  Query the database for the url of the html docket, if it exists
#
#          The json input is {"court": <court>,
#                             "casenum": <casenum>}
#
#          The json output is
#                            {"docket_url": <public url>,
#                             "timestamp": <last time seen> }
#     """
#     response = {}
#
#     if request.method != "POST":
#         message = "query_cases: Not a POST request."
#         logging.error(message)
#         return HttpResponse(message)
#
#     try:
#         jsonin = simplejson.loads(request.POST["json"])
#     except KeyError:
#         message = "query_cases: no 'json' POST argument"
#         logging.warning(message)
#         return HttpResponse(message)
#     except ValueError as err:
#         message = "query_cases: %s." % unicode(err)
#         logging.warning(message)
#         return HttpResponse(message)
#     except IOError:
#         message = "query_cases: Client read error (Timeout?)"
#         logging.warning(message)
#         return HttpResponse(message)
#
#     try:
#         court = jsonin["court"].strip()
#     except KeyError:
#         message = "query_cases: missing json 'court' argument."
#         logging.warning(message)
#         return HttpResponse(message)
#
#     try:
#         casenum = unicode(jsonin["casenum"])
#     except:
#         message = "query_cases: missing json 'casenum' argument."
#         logging.warning(message)
#         return HttpResponse(message)
#
#     doc_query = (Document.objects
#                          .filter(court=court)
#                          .filter(casenum=casenum)
#                          .order_by('-lastdate', '-modified'))
#
#     yesterday = datetime.datetime.now() - datetime.timedelta(1)
#
#     old_or_avail_query = doc_query.filter(available=1) | \
#                          doc_query.filter(modified__lte=yesterday)
#     query = None
#     try:
#         query = old_or_avail_query[0]
#     except IndexError:
#         try:
#             query = doc_query[0]
#         except IndexError:
#             query = None
#         else:
#             ppquery = PickledPut.objects.filter(
#                 filename=IACommon.get_docketxml_name(court, casenum))
#             if len(ppquery) > 0:
#                 query = None
#
#     if query:
#         try:
#             # we only have a last date for documents that have been uploaded
#             date = query.lastdate.strftime("%m/%d/%y")
#         except AttributeError:
#             try:
#                 date = query.modified.strftime("%m/%d/%y")
#             except AttributeError:
#                 date = "Unknown"
#
#         response = {
#             "docket_url": IACommon.get_dockethtml_url(court,
#                                                       casenum),
#             "timestamp": date}
#
#     jsonout = simplejson.dumps(response)
#     return HttpResponse(jsonout, mimetype="application/json")
#
#
# def adddocmeta(request):
#     """ add metadata to Document table on our server. """
#
#     if request.method != "POST":
#         message = "adddocmeta: Not a POST request."
#         logging.error(message)
#         return HttpResponse(message)
#
#     try:
#         docid = request.POST["docid"].strip()
#         court = request.POST["court"].strip()
#         casenum = request.POST["casenum"]
#         de_seq_num = int(request.POST["de_seq_num"])
#         dm_id = int(request.POST["dm_id"])
#         docnum = request.POST["docnum"]
#         subdocnum = 0
#     except KeyError as err:
#         message = "adddocmeta: %s not specified." % unicode(err)
#         logging.error(message)
#         return HttpResponse(message)
#     except ValueError as err:
#         message = "adddocmeta: %s." % unicode(err)
#         logging.error(message)
#         return HttpResponse(message)
#
#     # Necessary to preserve backwards compatibility with 0.6
#     #  This param prevents tons of garbage from being printed to
#     #  the error console after an Adddocmeta request
#     try:
#         add_case_info = request.POST["add_case_info"]
#     except KeyError:
#         add_case_info = None
#
#     DocumentManager.handle_adddocmeta(docid, court, casenum, de_seq_num,
#                                       dm_id, docnum, subdocnum)
#     if add_case_info:
#         response = {
#             "documents": UploadHandler._get_documents_dict(court, casenum),
#             "message": "adddocmeta: DB updated for docid=%s" % (docid)
#         }
#         message = simplejson.dumps(response)
#     else:
#         message = "adddocmeta: DB updated for docid=%s" % (docid)
#
#     return HttpResponse(message)
