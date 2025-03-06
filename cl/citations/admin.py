from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.citations.models import UnmatchedCitation


@admin.register(UnmatchedCitation)
class UnmatchedCitationAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "citing_opinion",
    )
    list_display_links = ("citing_opinion",)
    list_filter = ("type", "status")
    search_fields = (
        "volume",
        "reporter",
        "page",
    )
    raw_id_fields = ("citing_opinion",)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "status":
            # Show only integer values in the dropdown
            kwargs["choices"] = [
                (value, value) for value, _ in db_field.choices
            ]

            # Generate a new help text including both value and description
            choices_text = "<br>".join(
                f"<strong>{value}:</strong> {desc}"
                for value, desc in db_field.choices
            )
            kwargs["help_text"] = (
                f"<div>{db_field.help_text}</div><div>{choices_text}</div>"
            )

        return super().formfield_for_choice_field(db_field, request, **kwargs)
