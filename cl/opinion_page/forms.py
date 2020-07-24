import logging
from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.encoding import force_bytes
from django.utils.html import format_html

from cl.lib.crypto import sha1
from cl.people_db.models import Person
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.search.fields import (
    CeilingDateField,
    FloorDateField,
)
from cl.search.models import Court, Citation, Docket, Opinion


class CitationRedirectorForm(forms.Form):
    volume = forms.IntegerField(
        widget=forms.TextInput(
            attrs={"class": "form-control input-lg", "placeholder": "Volume",}
        ),
        required=True,
    )
    reporter = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control input-lg",
                "placeholder": "Reporter",
            }
        ),
        required=True,
    )
    page = forms.IntegerField(
        widget=forms.TextInput(
            attrs={"class": "form-control input-lg", "placeholder": "Page",}
        ),
        required=True,
    )


class DocketEntryFilterForm(forms.Form):
    ASCENDING = "asc"
    DESCENDING = "desc"
    DOCKET_ORDER_BY_CHOICES = (
        (ASCENDING, "Ascending"),
        (DESCENDING, "Descending"),
    )
    entry_gte = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
    )
    entry_lte = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
    )
    filed_after = FloorDateField(
        required=False,
        label="Filed After",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    filed_before = CeilingDateField(
        required=False,
        label="Filed Before",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    order_by = forms.ChoiceField(
        choices=DOCKET_ORDER_BY_CHOICES,
        required=False,
        label="Ordering",
        initial=ASCENDING,
        widget=forms.Select(),
    )


class TennWorkersForm(forms.Form):

    court_str = forms.CharField(required=True, widget=forms.HiddenInput(),)

    case_title = forms.CharField(
        label="Case Title",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Case Title",
                "autocomplete": "off",
            }
        ),
    )

    docket_number = forms.CharField(
        label="Docket Number",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Docket Number",
                "autocomplete": "off",
            }
        ),
    )

    publication_date = forms.DateField(
        label="Publication Date",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control datepicker",
                "placeholder": "Publication Date",
                "autocomplete": "off",
            }
        ),
    )

    lead_author = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=True,
        label="Lead Author",
        widget=forms.Select(
            attrs={
                "class": "form-control",
                "placeholder": "Choose Lead Author",
            }
        ),
    )

    second_judge = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Second Panelist",
        widget=forms.Select(attrs={"class": "form-control",}),
    )

    third_judge = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Third Panelist",
        widget=forms.Select(attrs={"class": "form-control",}),
    )

    cite_volume = forms.IntegerField(
        label="Cite Year",
        required=True,
        widget=forms.Select(
            choices=[(x, x) for x in xrange(datetime.now().year, 2013, -1)],
            attrs={"class": "form-control"},
        ),
    )

    cite_reporter = forms.CharField(label="Cite Reporter", required=True,)

    cite_page = forms.IntegerField(
        label="Cite Page",
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off",}
        ),
    )

    pdf_upload = forms.FileField(
        label="Opinion PDF",
        required=True,
        validators=[FileExtensionValidator(["pdf"])],
    )

    def __init__(self, *args, **kwargs):
        self.pk = kwargs.pop("pk", None)
        super(TennWorkersForm, self).__init__(*args, **kwargs)
        self.initial["court_str"] = self.pk
        self.initial["court"] = Court.objects.get(pk=self.pk)

        q_judges = Person.objects.filter(
            positions__court_id=self.pk, is_alias_of=None
        ).order_by("name_first")
        self.fields["lead_author"].queryset = q_judges
        self.fields["second_judge"].queryset = q_judges
        self.fields["third_judge"].queryset = q_judges

        if self.pk == "tennworkcompcl":
            self.fields["cite_reporter"].widget = forms.Select(
                choices=[("TN WC", "TN WC")], attrs={"class": "form-control"}
            )
            del self.fields["second_judge"]
            del self.fields["third_judge"]

        else:
            self.fields["cite_reporter"].widget = forms.Select(
                choices=[("TN WC App.", "TN WC App.")],
                attrs={"class": "form-control"},
            )

    def validate_neutral_citation(self):
        volume = self.cleaned_data["cite_volume"]
        reporter = self.cleaned_data["cite_reporter"]
        page = self.cleaned_data["cite_page"]

        c = Citation.objects.filter(
            volume=volume, reporter=reporter, page=page
        ).exists()
        if c:
            cite = Citation.objects.get(
                volume=volume, reporter=reporter, page=page
            )
            self.add_error(
                "cite_page",
                ValidationError(
                    format_html(
                        'Citation already in database. See: <a href="%s">%s</a>'
                        % (cite.get_absolute_url(), cite.cluster.case_name),
                    )
                ),
            )
        self.cleaned_data["neutral_citation"] = "%s %s %s" % (
            volume,
            reporter,
            page,
        )

    def clean_pdf_upload(self):
        pdf_data = self.cleaned_data.get("pdf_upload").read()
        sha_1 = sha1(force_bytes(pdf_data))
        exists = Opinion.objects.filter(sha1=sha_1).exists()
        if exists:
            op = Opinion.objects.get(sha1=sha_1)
            self.add_error(
                "pdf_upload",
                ValidationError(
                    format_html(
                        'Document already in database. See: <a href="%s">%s</a>'
                        % (op.get_absolute_url(), op.cluster.case_name),
                    )
                ),
            )
        return pdf_data

    def make_panel(self):
        if self.pk == "tennworkcompapp":
            self.cleaned_data["panel"] = [
                self.cleaned_data["lead_author"],
                self.cleaned_data.get("second_judge"),
                self.cleaned_data.get("third_judge"),
            ]
        else:
            self.cleaned_data["panel"] = [self.cleaned_data["lead_author"]]

    def make_item_dict(self):
        self.cleaned_data["item"] = {
            "case_names": self.cleaned_data.get("case_title"),
            "case_dates": self.cleaned_data["publication_date"],
            "precedential_statuses": "Published",
            "docket_numbers": self.cleaned_data["docket_number"],
            "judges": ", ".join(
                [j.name_full for j in self.cleaned_data.get("panel")]
            ),
            "author_id": self.cleaned_data["lead_author"].id,
            "author": self.cleaned_data["lead_author"],
            "date_filed_is_approximate": "False",
            "blocked_statuses": "False",
            "neutral_citations": self.cleaned_data["neutral_citation"],
            "download_urls": "",
        }

    def clean(self):
        super(TennWorkersForm, self).clean()
        self.validate_neutral_citation()
        self.make_panel()
        self.make_item_dict()
        return self.cleaned_data

    def save(self):
        """Save uploaded Tennessee Workers Comp/Appeal to db.

        :return: Cluster ID
        """

        sha1_hash = sha1(force_bytes(self.cleaned_data.get("pdf_upload")))
        court = Court.objects.get(pk=self.cleaned_data.get("court_str"))

        docket, opinion, cluster, citations, error = make_objects(
            self.cleaned_data.get("item"),
            court,
            sha1_hash,
            self.cleaned_data.get("pdf_upload"),
        )

        if error:
            raise ValidationError("PDF failed to upload. %s")

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            },
            index=True,
        )

        extract_doc_content.delay(
            opinion.pk, do_ocr=True, citation_jitter=True,
        )

        logging.info(
            "Successfully added Tennessee object cluster: %s", cluster.id
        )

        return cluster.id
