from typing import Awaitable, Callable

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponseBase
from django.template.response import TemplateResponse


class RobotsHeaderMiddleware:
    """Adds x-robots-tag HTTP header to any request that has `private=True`

    There's some evidence and good logic to support the idea that using the
    x-robots-tag HTTP header uses less of a site's "crawl budget" than
    using the noindex HTML tag. Logically, this makes sense because crawlers
    can simply download the headers and stop, instead of downloading and
    parsing pages.

    Because we have good measures to make sure that the `private` context
    variable is set on every page, this middleware uses that variable to set
    the HTTP headers too.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(self.get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self.__acall__(request)
        response = self.get_response(request)
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        response = await self.get_response(request)
        return response

    def process_template_response(
        self,
        request: HttpRequest,
        response: TemplateResponse,
    ) -> TemplateResponse:
        if getattr(response, "context_data", None) is None:
            return response

        private = False
        if response.context_data:
            private = response.context_data.get("private", False)
        if private:
            response.headers["X-Robots-Tag"] = (
                "noindex, noarchive, noimageindex"
            )
        return response
