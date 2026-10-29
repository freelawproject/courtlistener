from collections.abc import Callable, Coroutine
from functools import wraps
from http import HTTPStatus
from typing import Any, Concatenate

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from cl.search.models import ClusterRedirection


def handle_cluster_redirection[**P](
    view_func: Callable[
        Concatenate[HttpRequest, P], Coroutine[Any, Any, HttpResponse]
    ],
) -> Callable[Concatenate[HttpRequest, P], Coroutine[Any, Any, HttpResponse]]:
    """
    Redirect from deleted clusters to existing clusters

    Uses the ClusterRedirection table, and only changed the `pk` of the request
    """

    @wraps(view_func)
    async def _wrapped_view(
        request: HttpRequest, *args: P.args, **kwargs: P.kwargs
    ) -> HttpResponse:
        try:
            response = await view_func(request, *args, **kwargs)
            return response
        except Http404 as exc:
            try:
                redirection = await ClusterRedirection.objects.aget(
                    deleted_cluster_id=kwargs["pk"]
                )
            except ClusterRedirection.DoesNotExist:
                raise exc

            if redirection.reason == ClusterRedirection.SEALED:
                return TemplateResponse(
                    request, "410.html", status=HTTPStatus.GONE
                )

            cluster_id = redirection.cluster_id

            # Without a resolved, named route there is no URL to rebuild.
            if request.resolver_match is None:
                raise exc
            url_name = request.resolver_match.url_name
            if url_name is None:
                raise exc

            # redirect to the same URL, only change the target PK
            url_kwargs = dict(kwargs)
            url_kwargs["pk"] = cluster_id
            return redirect(url_name, permanent=True, **url_kwargs)

    return _wrapped_view
