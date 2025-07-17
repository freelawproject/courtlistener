from functools import wraps

from django.http import Http404
from django.shortcuts import redirect

from cl.search.models import ClusterRedirection


def handle_cluster_redirection(view_func):
    """
    Redirect from deleted clusters to existing clusters

    Uses the ClusterRedirection table, and only changed the `pk` of the request
    """

    @wraps(view_func)
    async def _wrapped_view(request, *args, **kwargs):
        try:
            response = await view_func(request, *args, **kwargs)
            return response
        except Http404 as exc:
            try:
                redirection = await ClusterRedirection.objects.aget(
                    deleted_cluster_id=kwargs["pk"]
                )
                cluster_id = redirection.cluster_id

                if not cluster_id:
                    # TODO: should redirect to sealed page
                    raise exc
            except ClusterRedirection.DoesNotExist:
                raise exc

            # redirect to the same URL, only change the target PK
            url_name = request.resolver_match.url_name
            url_kwargs = kwargs.copy()
            url_kwargs["pk"] = cluster_id
            url_kwargs["permanent"] = True
            return redirect(url_name, **url_kwargs)

    return _wrapped_view
