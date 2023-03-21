# Use this test to ensure that your python binary and virtualenvs are set up
# properly.
import locale
import sys


def application(environ, start_response):
    status = "200 OK"

    output = ""
    output += f"sys.version = {repr(sys.version)}\n"
    output += f"sys.prefix = {repr(sys.prefix)}\n"
    output += f"sys.path = {repr(sys.path)}\n"
    output += f"locale.getlocale() = {repr(locale.getlocale())}\n"
    output += (
        f"locale.getdefaultlocale() = {repr(locale.getdefaultlocale())}\n"
    )
    output += (
        f"sys.getfilesystemencoding() = {repr(sys.getfilesystemencoding())}\n"
    )
    output += f"sys.getdefaultencoding() = {repr(sys.getdefaultencoding())}\n"
    output += "locale.getpreferredencoding(False): %s\n" % repr(
        locale.getpreferredencoding(False)
    )

    output += "\n\n"
    output += (
        f"mod_wsgi.process_group = {repr(environ['mod_wsgi.process_group'])}"
    )

    response_headers = [
        ("Content-type", "text/plain"),
        ("Content-Length", str(len(output))),
    ]
    start_response(status, response_headers)

    return [output.encode("UTF-8")]
