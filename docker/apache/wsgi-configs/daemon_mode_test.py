# Use this configuration to see if WSGI is correctly being used in daemon mode.
# If so, it'll output that mod_wsgi.process_group = *something*.
# See: http://blog.dscpl.com.au/2012/10/why-are-you-using-embedded-mode-of.html


def application(environ, start_response):
    status = "200 OK"

    name = repr(environ["mod_wsgi.process_group"])
    output = "mod_wsgi.process_group = %s" % name

    response_headers = [
        ("Content-type", "text/plain"),
        ("Content-Length", str(len(output))),
    ]
    start_response(status, response_headers)

    return [output]
