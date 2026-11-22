"""View decorators that set up view tracking in the template context."""

from collections.abc import Coroutine
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.template.response import SimpleTemplateResponse

from cl.lib.types import DjangoViewDecorator, DjangoViewType


def track_view_counter[
    **P,
    Request: HttpRequest,
    Response: HttpResponse | Coroutine[Any, Any, HttpResponse],
](tracks: str, label_format: str) -> DjangoViewDecorator[P, Request, Response]:
    """Decorator to injects a tracking label into template responses for event counting (e.g., view tracking).

    This decorator is meant to be used on views that return a
    SimpleTemplateResponse. It will extract a model instance from the response's
    context using the provided `tracks` key, generate a label using
    `label_format`, and inject that label into the context for use in templates
    or client-side analytics.

    Unlike a full tracking system, this decorator does NOT directly increment
    or persist any count. Instead, it marks the response with an `event_label`
    and a `track_events` flag, which can be used elsewhere (e.g., in middleware
    or frontend JavaScript) to handle actual counting logic.

    Args:
        tracks (str): The name of the attribute within the view's context_data
                      that holds the model instance (record) being tracked.
                      For example, if your context is {'docket': docket_obj},
                      'tracks' would be 'docket'.
        label_format (str): A format string used to generate the unique label
                            for the GenericCount record. It should expect one
                            placeholder for the model's ID (e.g., 'd.%s:view').
    """

    def decorator(
        func: DjangoViewType[P, Request, Response],
    ) -> DjangoViewType[P, Request, Response]:
        def _add_tracking(response: SimpleTemplateResponse) -> None:
            """Adds the tracking label for the tracked model to the response's context.

            The model is read from the response's context_data under
            ``tracks``, and its ID is formatted into ``label_format``.

            Args:
                response: The response whose context holds the tracked model.

            Raises:
                TypeError: If the response has no context data.
            """
            if (context_data := response.context_data) is None:
                raise TypeError(
                    f"Response context_data is None (attempting to track {tracks})"
                )
            model = context_data[tracks]
            context_data.update(
                {"event_label": label_format % model.id, "track_events": True}
            )

        if iscoroutinefunction(func):

            @wraps(func)
            async def inner(
                request: Request, *args: P.args, **kwargs: P.kwargs
            ) -> Response:
                response = await func(request, *args, **kwargs)
                if not isinstance(response, SimpleTemplateResponse):
                    return response

                await sync_to_async(_add_tracking)(response)
                return cast(Response, response)

        else:

            @wraps(func)
            def inner(
                request: Request, *args: P.args, **kwargs: P.kwargs
            ) -> Response:
                response = func(request, *args, **kwargs)
                if not isinstance(response, SimpleTemplateResponse):
                    return response

                _add_tracking(response)
                return response

        return cast(DjangoViewType[P, Request, Response], inner)

    return decorator
