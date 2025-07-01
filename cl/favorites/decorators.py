from functools import wraps

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.template.response import SimpleTemplateResponse


def track_view_counter(tracks=str, label_format=str):
    """
    Decorator to injects a tracking label into template responses for event
    counting (e.g., view tracking).

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

    def decorator(func):
        def _get_label(
            response: SimpleTemplateResponse,
            track_attribute: str,
            template: str,
        ) -> int:
            """
            Generates a tracking label string based on a model instance found
            in the response.

            This helper function extracts a model instance from the response's
            context_data using the provided key, then formats a label using the
            supplied format string and the instance's ID.

            Args:
                response (SimpleTemplateResponse): The response object containing
                context data.
                track_attribute (str): The key in context_data for the tracked
                model.
                template (str): The format string for the GenericCount label.

            Returns:
                A formatted tracking label.
            """
            model = response.context_data[track_attribute]
            label = template % (model.id)
            return label

        if iscoroutinefunction(func):

            @wraps(func)
            async def inner(request, *args, **kwargs):
                response = await func(request, *args, **kwargs)
                if not isinstance(response, SimpleTemplateResponse):
                    return response

                event_label = await sync_to_async(_get_label)(
                    response, tracks, label_format
                )
                response.context_data.update(
                    {"event_label": event_label, "track_events": True}
                )
                return response

        else:

            @wraps(func)
            def inner(request, *args, **kwargs):
                response = func(request, *args, **kwargs)
                if not isinstance(response, SimpleTemplateResponse):
                    return response

                event_label = _get_label(response, tracks, label_format)
                response.context_data.update(
                    {"event_label": event_label, "track_events": True}
                )
                return response

        return inner

    return decorator
