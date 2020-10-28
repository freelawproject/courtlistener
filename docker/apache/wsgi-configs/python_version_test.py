# Use this test to ensure that your python binary and virtualenvs are set up
# properly.
import locale
import sys


def application(environ, start_response):
    status = "200 OK"

    output = u""
    output += u"sys.version = %s\n" % repr(sys.version)
    output += u"sys.prefix = %s\n" % repr(sys.prefix)
    output += u"sys.path = %s\n" % repr(sys.path)
    output += u"locale.getlocale() = %s\n" % repr(locale.getlocale())
    output += u"locale.getdefaultlocale() = %s\n" % repr(
        locale.getdefaultlocale()
    )
    output += u"sys.getfilesystemencoding() = %s\n" % repr(
        sys.getfilesystemencoding()
    )
    output += u"sys.getdefaultencoding() = %s\n" % repr(
        sys.getdefaultencoding()
    )
    output += u"locale.getpreferredencoding(False): %s\n" % repr(
        locale.getpreferredencoding(False)
    )

    output += "\n\n"
    output += "mod_wsgi.process_group = %s" % repr(
        environ["mod_wsgi.process_group"]
    )

    response_headers = [
        ("Content-type", "text/plain"),
        ("Content-Length", str(len(output))),
    ]
    start_response(status, response_headers)

    return [output.encode("UTF-8")]
