BASE_DOWNLOAD_URL = "https://www.archive.org/download"


def get_bucketname(court, casenum):
    bucketlist = ["gov", "uscourts", court, unicode(casenum)]
    return ".".join(bucketlist)


def get_docketxml_url(court, casenum):
    return "%s/%s/%s" % (
        BASE_DOWNLOAD_URL,
        get_bucketname(court, casenum),
        get_docket_filename(court, casenum),
    )


def get_pdf_url(court, casenum, filename):
    return "%s/%s/%s" % (
        BASE_DOWNLOAD_URL,
        get_bucketname(court, casenum),
        filename,
    )


def get_docket_filename(court, casenum):
    return ".".join(["gov", "uscourts", unicode(court), unicode(casenum),
                     "docket.xml"])


def get_document_filename(court, casenum, docnum, subdocnum):
    return ".".join(["gov", "uscourts", unicode(court), unicode(casenum),
                     unicode(docnum), unicode(subdocnum), "pdf"])
