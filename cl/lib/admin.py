from typing import Any, TypedDict
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models import Model, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from cl.lib.models import Note


class AdminTweaksMixin:
    class Media:
        css = {
            "all": ("css/admin.css",),
        }


class NotesInline(GenericTabularInline):
    model = Note
    extra = 1


def build_admin_url(
    model_class: type[Model],
    query_params: dict[str, Any] | None = None,
) -> str:
    """
    Construct a URL for a given model's admin view, optionally appending query parameters.

    :param model_class: The Django model class for which the admin URL will be built.
    :param query_params: A dictionary of query parameters to append to the URL (e.g. {"docket": 123}).
    :return: A string representing the fully constructed admin URL, including any query parameters.

    Example usage:
        >>> from cl.search.models import DocketEntry
        >>> build_admin_url(DocketEntry, {"docket": "1234"})
        '/admin/search/docketentry/?docket=1234'
    """
    query_params = query_params or {}
    app_label = model_class._meta.app_label
    model_name = model_class._meta.model_name
    # "admin:app_label_modelname_changelist" is the standard naming for admin changelist
    entries_changelist_url = reverse(
        f"admin:{app_label}_{model_name}_changelist"
    )
    encoded_query_params = urlencode(query_params)
    return f"{entries_changelist_url}?{encoded_query_params}"


class AdminLinkConfig(TypedDict):
    label: str
    model_class: type[Model]
    query_params: dict[str, Any] | None


class AdminLink(TypedDict):
    href: str
    label: str


def generate_admin_links(
    links: list[AdminLinkConfig],
) -> list[AdminLink]:
    """
    Construct a list of links with links to given admin views.
    Each link should have the following keys:
    - label: Label for the link.
    - model_class: The Django model class for which the admin URL will be built.
    - query_params: Query parameters to append to the URL (e.g. {"docket": 123}).
    """
    generated_links: list[AdminLink] = []

    for link in links:
        generated_links.append(
            {
                "href": build_admin_url(
                    link["model_class"],
                    query_params=link["query_params"],
                ),
                "label": link["label"],
            }
        )

    return generated_links


class IndexedPkSearchMixin:
    """Search a large table by PK without the admin's varchar cast

    Django's admin search builds an `icontains` lookup for every entry in
    `search_fields`, casting non-text fields to `CharField` to do so. That cast
    stops Postgres from using the primary key index, which makes the changelist
    search time out on our biggest tables. Comparing the integer ourselves keeps
    the lookup on the index.

    This was fixed upstream in Django 6.1, which no longer casts primary keys,
    so this mixin can be deleted once we're running 6.1.

    Admins using this mixin MUST still set a non-empty `search_fields` (e.g.
    `("pk",)`), because the admin reads it to decide whether to render the
    search box at all. Its contents are otherwise ignored: only the PK is
    searched, and non-numeric input matches nothing, which is what the admin
    does for any search that comes up empty.

    Must be listed before `ModelAdmin` in the bases so that it wins the MRO.

    See: https://github.com/freelawproject/courtlistener/issues/6790
    """

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet, search_term: str
    ) -> tuple[QuerySet, bool]:
        """Filter the changelist queryset down to an exact PK match

        :param request: The current HTTP request.
        :param queryset: The changelist queryset to filter.
        :param search_term: The raw string typed into the search box.
        :return: Two-tuple of the filtered queryset and whether the caller
            needs to de-duplicate the results (never, here).
        """
        if not search_term:
            return queryset, False

        try:
            pk = int(search_term.strip())
        except ValueError:
            return queryset.none(), False

        return queryset.filter(pk=pk), False


class SealableDocumentAdmin(admin.ModelAdmin):
    """Mixin for admin classes that support sealing RECAP documents
    via a confirmation page and bulk actions.

    Subclasses must define:
        seal_url_name: URL name for the seal confirmation route
            (e.g. "recapdocument_seal_confirmation")
        seal_link_label: Label for the custom link on the change form
            (e.g. "Seal Document")
        seal_heading_template: Format string for the confirmation heading,
            with {pk} placeholder (e.g. "Seal RECAP Document #{pk}?")
        seal_model: The model class to look up by pk for the confirmation
            view (e.g. RECAPDocument or DocketEntry)
        seal_change_url_name: URL name for the model's admin change view
            (e.g. "admin:search_recapdocument_change")

    Subclasses must implement:
        get_seal_documents(obj): Return an iterable of RECAPDocuments
            to display on the confirmation page for the given object.
    """

    seal_url_name: str = ""
    seal_link_label: str = ""
    seal_heading_template: str = ""
    seal_model: type[Model]
    seal_change_url_name: str = ""

    def get_seal_documents(self, obj: Model) -> list | QuerySet:
        """Return the RECAPDocuments to seal for the given object.

        :param obj: The model instance from the confirmation view.
        :return: List or QuerySet of RECAPDocument instances.
        """
        raise NotImplementedError

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "seal-confirmation/<int:pk>/",
                self.admin_site.admin_view(self.seal_confirmation_view),
                name=self.seal_url_name,
            ),
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        seal_url = reverse(
            f"admin:{self.seal_url_name}",
            args=[object_id],
        )
        # Preserve any existing custom_links from subclasses
        custom_links = extra_context.get("custom_links", [])
        custom_links.append({"href": seal_url, "label": self.seal_link_label})
        extra_context["custom_links"] = custom_links
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def seal_confirmation_view(
        self, request: HttpRequest, pk: int
    ) -> HttpResponse:
        """Render a seal confirmation page (GET) or seal selected
        documents (POST)."""
        obj = get_object_or_404(self.seal_model, pk=pk)
        documents = self.get_seal_documents(obj)
        heading = self.seal_heading_template.format(pk=pk)

        if request.method == "POST":
            self._seal_and_report(request)
            return HttpResponseRedirect(
                reverse(self.seal_change_url_name, args=[pk])
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Confirm document sealing",
            "heading": heading,
            "documents": documents,
            # The template builds the cancel link with {% url %} rather than
            # dropping a prebuilt string straight into an href.
            "cancel_url_name": self.seal_change_url_name,
            "object_pk": pk,
        }
        return render(
            request,
            "admin/seal_document_confirmation.html",
            context,
        )

    def _seal_and_report(
        self,
        request: HttpRequest,
        queryset: QuerySet | None = None,
    ) -> None:
        """Seal documents and report success/failure via admin messages.

        When called without a queryset (from the confirmation POST handler),
        reads doc_ids from request.POST. When called with a queryset (from
        a bulk action), seals those documents directly.

        :param request: The current HTTP request.
        :param queryset: QuerySet of RECAPDocuments to seal (bulk action).
        """
        from cl.search.models import RECAPDocument
        from cl.search.utils import seal_documents

        if queryset is None:
            doc_ids = request.POST.getlist("doc_ids")
            queryset = RECAPDocument.objects.filter(pk__in=doc_ids)

        ia_failures = seal_documents(queryset)
        sealed_count = queryset.count()

        if ia_failures:
            self.message_user(
                request,
                f"Sealed {sealed_count} document(s), but failed to "
                f"remove {len(ia_failures)} item(s) from Internet "
                f"Archive: {ia_failures}",
                messages.WARNING,
            )
        else:
            self.message_user(
                request,
                f"Successfully sealed and removed {sealed_count} document(s).",
                messages.SUCCESS,
            )
