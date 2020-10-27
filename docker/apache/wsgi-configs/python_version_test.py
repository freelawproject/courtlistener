# Use this test to ensure that your python binary and virtualenvs are set up
# properly.

import sys


def application(environ, start_response):
    status = "200 OK"

    output = u""
    output += u"sys.version = %s\n" % repr(sys.version)
    output += u"sys.prefix = %s\n" % repr(sys.prefix)
    output += u"sys.path = %s\n" % repr(sys.path)

    response_headers = [
        ("Content-type", "text/plain"),
        ("Content-Length", str(len(output))),
    ]
    start_response(status, response_headers)

    return [output.encode("UTF-8")]
