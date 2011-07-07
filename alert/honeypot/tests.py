from django.test import TestCase
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.template import Template, Context
from django.template.loader import render_to_string
from django.conf import settings
from honeypot.middleware import HoneypotViewMiddleware, HoneypotResponseMiddleware
from honeypot.decorators import verify_honeypot_value, check_honeypot

def _get_GET_request():
    return HttpRequest()

def _get_POST_request():
    req = HttpRequest()
    req.method = "POST"
    return req

def view_func(request):
    return HttpResponse()

class HoneypotTestCase(TestCase):
    def setUp(self):
        # delattrs here are a required hack until django #10130 is closed
        if hasattr(settings, 'HONEYPOT_VALUE'):
            delattr(settings._wrapped, 'HONEYPOT_VALUE')
        if hasattr(settings, 'HONEYPOT_VERIFIER'):
            delattr(settings._wrapped, 'HONEYPOT_VERIFIER')
        settings.HONEYPOT_FIELD_NAME = 'honeypot'

class VerifyHoneypotValue(HoneypotTestCase):

    def test_no_call_on_get(self):
        """ test that verify_honeypot_value is not called when request.method == GET """
        request = _get_GET_request()
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp, None)

    def test_verifier_false(self):
        """ test that verify_honeypot_value fails when HONEYPOT_VERIFIER returns False """
        request = _get_POST_request()
        request.POST[settings.HONEYPOT_FIELD_NAME] = ''
        settings.HONEYPOT_VERIFIER = lambda x: False
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp.__class__, HttpResponseBadRequest)

    def test_field_missing(self):
        """ test that verify_honeypot_value succeeds when HONEYPOT_FIELD_NAME is missing from request.POST """
        request = _get_POST_request()
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp.__class__, HttpResponseBadRequest)

    def test_field_blank(self):
        """ test that verify_honeypot_value succeeds when HONEYPOT_VALUE is blank """
        request = _get_POST_request()
        request.POST[settings.HONEYPOT_FIELD_NAME] = ''
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp, None)

    def test_honeypot_value_string(self):
        """ test that verify_honeypot_value succeeds when HONEYPOT_VALUE is a string """
        request = _get_POST_request()
        settings.HONEYPOT_VALUE = '(test string)'
        request.POST[settings.HONEYPOT_FIELD_NAME] = settings.HONEYPOT_VALUE
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp, None)

    def test_honeypot_value_callable(self):
        """ test that verify_honeypot_value succeeds when HONEYPOT_VALUE is a callable """
        request = _get_POST_request()
        settings.HONEYPOT_VALUE = lambda: '(test string)'
        request.POST[settings.HONEYPOT_FIELD_NAME] = settings.HONEYPOT_VALUE()
        resp = verify_honeypot_value(request, None)
        self.assertEquals(resp, None)


class CheckHoneypotDecorator(HoneypotTestCase):

    def test_default_decorator(self):
        """ test that @check_honeypot works and defaults to HONEYPOT_FIELD_NAME """
        new_view_func = check_honeypot(view_func)
        request = _get_POST_request()
        resp = new_view_func(request)
        self.assertEquals(resp.__class__, HttpResponseBadRequest)

    def test_decorator_argument(self):
        """ test that check_honeypot(view, 'fieldname') works """
        new_view_func = check_honeypot(view_func, 'fieldname')
        request = _get_POST_request()
        resp = new_view_func(request)
        self.assertEquals(resp.__class__, HttpResponseBadRequest)

    def test_decorator_py24_syntax(self):
        """ test that @check_honeypot syntax works """
        @check_honeypot('field')
        def new_view_func(request):
            return HttpResponse()
        request = _get_POST_request()
        resp = new_view_func(request)
        self.assertEquals(resp.__class__, HttpResponseBadRequest)

class RenderHoneypotField(HoneypotTestCase):

    def _assert_rendered_field(self, template, fieldname, value=''):
        correct = render_to_string('honeypot/honeypot_field.html', 
                                   {'fieldname':fieldname, 'value': value})
        rendered = template.render(Context())
        self.assertEquals(rendered, correct)

    def test_default_templatetag(self):
        """ test that {% render_honeypot_field %} works and defaults to HONEYPOT_FIELD_NAME """
        template = Template('{% load honeypot %}{% render_honeypot_field %}')
        self._assert_rendered_field(template, settings.HONEYPOT_FIELD_NAME, '')

    def test_templatetag_honeypot_value(self):
        """ test that {% render_honeypot_field %} uses settings.HONEYPOT_VALUE """
        template = Template('{% load honeypot %}{% render_honeypot_field %}')
        settings.HONEYPOT_VALUE = '(leave blank)'
        self._assert_rendered_field(template, settings.HONEYPOT_FIELD_NAME, settings.HONEYPOT_VALUE)

    def test_templatetag_argument(self):
        """ test that {% render_honeypot_field 'fieldname' %} works """
        template = Template('{% load honeypot %}{% render_honeypot_field "fieldname" %}')
        self._assert_rendered_field(template, 'fieldname', '')

class HoneypotMiddleware(HoneypotTestCase):

    _response_body = '<form method="POST"></form>'

    def test_view_middleware_invalid(self):
        """ don't call view when HONEYPOT_VERIFIER returns False """
        request = _get_POST_request()
        retval = HoneypotViewMiddleware().process_view(request, view_func, (), {})
        self.assertEquals(retval.__class__, HttpResponseBadRequest)

    def test_view_middleware_valid(self):
        """ call view when HONEYPOT_VERIFIER returns True """
        request = _get_POST_request()
        request.POST[settings.HONEYPOT_FIELD_NAME] = ''
        retval = HoneypotViewMiddleware().process_view(request, view_func, (), {})
        self.assertEquals(retval, None)

    def test_response_middleware_rewrite(self):
        """ ensure POST forms are rewritten """
        request = _get_POST_request()
        request.POST[settings.HONEYPOT_FIELD_NAME] = ''
        response = HttpResponse(self._response_body)
        HoneypotResponseMiddleware().process_response(request, response)
        self.assertNotEqual(response.content, self._response_body)
        self.assertContains(response, 'name="%s"' % settings.HONEYPOT_FIELD_NAME)

    def test_response_middleware_contenttype_exclusion(self):
        """ ensure POST forms are not rewritten for non-html content types """
        request = _get_POST_request()
        request.POST[settings.HONEYPOT_FIELD_NAME] = ''
        response = HttpResponse(self._response_body, content_type='text/javascript')
        HoneypotResponseMiddleware().process_response(request, response)
        self.assertEquals(response.content, self._response_body)

    def test_response_middleware_unicode(self):
        """ ensure that POST form rewriting works with unicode templates """
        request = _get_GET_request()
        unicode_body = u'\u2603'+self._response_body    # add unicode snowman
        response = HttpResponse(unicode_body)
        HoneypotResponseMiddleware().process_response(request, response)
        self.assertNotEqual(response.content, unicode_body)
        self.assertContains(response, 'name="%s"' % settings.HONEYPOT_FIELD_NAME)
