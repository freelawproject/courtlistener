import logging
from datetime import datetime
from typing import Any, MutableMapping

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.encoding import force_bytes
from django.utils.html import format_html

from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.people_db.models import Person
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.search.fields import CeilingDateField, FloorDateField
from cl.search.models import (
    SOURCES,
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)


class CitationRedirectorForm(forms.Form):
    volume = forms.IntegerField(
        widget=forms.TextInput(
            attrs={"class": "form-control input-lg", "placeholder": "Volume"}
        ),
        required=False,
    )
    # We change the place holder to allow people to continue to use the rest
    # of the redirect API with no modifications.
    reporter = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control input-lg",
                "placeholder": "Paste any text containing a citation",
            }
        ),
        required=True,
    )
    page = forms.IntegerField(
        widget=forms.TextInput(
            attrs={"class": "form-control input-lg", "placeholder": "Page"}
        ),
        required=False,
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

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super(DocketEntryFilterForm, self).__init__(*args, **kwargs)

    def clean_order_by(self):
        data = self.cleaned_data["order_by"]
        if data:
            return data
        if not self.request.user.is_authenticated:
            return data
        user: UserProfile.user = self.request.user
        if user.profile.docket_default_order_desc:
            return DocketEntryFilterForm.DESCENDING
        return data


class CourtUploadForm(forms.Form):
    initial: MutableMapping[str, Any]

    court_str = forms.CharField(required=True, widget=forms.HiddenInput())
    case_title = forms.CharField(
        label="Caption",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Caption",
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
    date_argued = forms.DateField(
        label="Argued Date",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control datepicker",
                "placeholder": "Argued Date",
                "autocomplete": "off",
            }
        ),
    )
    date_reargued = forms.DateField(
        label="Reargued Date",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control datepicker",
                "placeholder": "Reargued Date",
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
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    third_judge = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Third Panelist",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    panel = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        required=True,
        label="Panel",
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control input-lg",
                "height": "100%",
                "size": "10",
            }
        ),
    )
    cite_volume = forms.IntegerField(
        label="Cite Year",
        required=True,
        widget=forms.Select(
            choices=[(x, x) for x in range(datetime.now().year, 2013, -1)],
            attrs={"class": "form-control"},
        ),
    )
    cite_reporter = forms.CharField(
        label="Cite Reporter",
        required=True,
    )
    cite_page = forms.IntegerField(
        label="Cite Page",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
            }
        ),
    )
    pdf_upload = forms.FileField(
        label="Opinion PDF",
        required=True,
        validators=[FileExtensionValidator(["pdf"])],
        widget=forms.FileInput(attrs={"accept": ".pdf"}),
    )

    def __init__(self, *args, **kwargs) -> None:
        self.pk = kwargs.pop("pk", None)
        super(CourtUploadForm, self).__init__(*args, **kwargs)
        self.initial["court_str"] = self.pk
        self.initial["court"] = Court.objects.get(pk=self.pk)

        if self.pk == "me":
            # The court requested the order of the panel match the seniority
            # of the judges, in order or date joined after sorting by pos type
            # Chief, Associate, Retired Active
            # Additionally, we only want active justices so remove them if
            # terminated or retired, without a new role being created as an
            # retired active justice
            q_judges = (
                Person.objects.filter(
                    (
                        (
                            Q(positions__position_type="c-jus")
                            | Q(positions__position_type="ass-jus")
                            | Q(positions__position_type="ret-act-jus")
                        )
                        & (
                            Q(positions__date_termination__isnull=True)
                            & Q(positions__date_retirement__isnull=True)
                        )
                    ),
                    positions__court_id="me",
                    is_alias_of=None,
                )
                .annotate(
                    custom_order=Case(
                        When(positions__position_type="c-jus", then=Value(1)),
                        When(
                            positions__position_type="ass-jus", then=Value(2)
                        ),
                        When(
                            positions__position_type="ret-act-jus",
                            then=Value(3),
                        ),
                        output_field=IntegerField(),
                    )
                )
                .order_by("custom_order", "positions__date_start")
            )
        else:
            q_judges = Person.objects.filter(
                positions__court_id=self.pk, is_alias_of=None
            ).order_by("name_first")

        for field_name in [
            "lead_author",
            "second_judge",
            "third_judge",
            "panel",
        ]:
            self.fields[field_name].queryset = q_judges  # type: ignore[attr-defined]
            self.fields[field_name].label_from_instance = self.person_label  # type: ignore[attr-defined]

        if self.pk == "tennworkcompcl":
            self.fields["cite_reporter"].widget = forms.Select(
                choices=[("TN WC", "TN WC")],
                attrs={"class": "form-control"},
            )
            self.drop_fields(
                [
                    "date_argued",
                    "date_reargued",
                    "panel",
                    "second_judge",
                    "third_judge",
                ]
            )

        elif self.pk == "me":
            self.fields["cite_reporter"].widget = forms.Select(
                choices=[("ME", "ME")],
                attrs={"class": "form-control"},
            )
            self.drop_fields(["lead_author", "second_judge", "third_judge"])
        elif self.pk == "tennworkcompapp":
            self.fields["cite_reporter"].widget = forms.Select(
                choices=[("TN WC App.", "TN WC App.")],
                attrs={"class": "form-control"},
            )
            self.drop_fields(["date_argued", "date_reargued", "panel"])
        else:
            raise BaseException

        self.fields["cite_reporter"].widget.attrs["readonly"] = True

    def drop_fields(self, fields: list[str]) -> None:
        """Remove fields not used in other courts

        When we add more courts we may need to find a better way to handle this.

        :param fields: Fields as a list not used
        :return: None
        """
        for field in fields:
            del self.fields[field]

    @staticmethod
    def person_label(obj) -> str:
        return obj.name_full

    def validate_neutral_citation(self) -> None:
        volume = self.cleaned_data["cite_volume"]
        reporter = self.cleaned_data["cite_reporter"]
        page = self.cleaned_data["cite_page"]

        c = Citation.objects.filter(
            volume=volume, reporter=reporter, page=page
        )
        if len(c):
            cite = c[0]
            self.add_error(
                "cite_page",
                ValidationError(
                    format_html(
                        'Citation already in database. See: <a href="%s">%s</a>'
                        % (cite.get_absolute_url(), cite.cluster.case_name),
                    )
                ),
            )
        self.cleaned_data["citations"] = f"{volume} {reporter} {page}"

    def verify_unique_judges(self) -> None:
        if self.pk == "tennworkcompapp":
            judges = [
                self.cleaned_data["lead_author"],
                self.cleaned_data["second_judge"],
                self.cleaned_data["third_judge"],
            ]
            flag = len(set(judges)) == len(judges)
            if not flag:
                self.add_error(
                    "lead_author",
                    ValidationError("Please select each judge only once."),
                )

    def clean_pdf_upload(self) -> bytes:
        pdf_data = self.cleaned_data["pdf_upload"].read()
        sha1_hash = sha1(force_bytes(pdf_data))
        ops = Opinion.objects.filter(sha1=sha1_hash)
        if len(ops) > 0:
            op = ops[0]
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

    def make_panel(self) -> None:
        if self.pk == "tennworkcompapp":
            self.cleaned_data["panel"] = list(
                filter(
                    None,
                    [
                        self.cleaned_data["lead_author"],
                        self.cleaned_data.get("second_judge"),
                        self.cleaned_data.get("third_judge"),
                    ],
                )
            )
        elif self.pk == "me":
            self.cleaned_data["panel"] = self.cleaned_data["panel"]
        else:
            self.cleaned_data["panel"] = [self.cleaned_data["lead_author"]]

    def make_item_dict(self) -> None:
        """Make item dictionary for adding to our DB

        :return: None
        """
        lead_author = self.cleaned_data.get("lead_author")
        self.cleaned_data["item"] = {
            "source": Docket.DIRECT_INPUT,
            "cluster_source": SOURCES.DIRECT_COURT_INPUT,
            "case_names": self.cleaned_data.get("case_title"),
            "case_dates": self.cleaned_data["publication_date"],
            "precedential_statuses": "Published",
            "docket_numbers": self.cleaned_data["docket_number"],
            "judges": ", ".join(
                [j.name_full for j in self.cleaned_data["panel"]]
            ),
            "author_id": lead_author.id if lead_author else None,
            "author": lead_author,
            "date_filed_is_approximate": False,
            "blocked_statuses": False,
            "citations": self.cleaned_data["citations"],
            "download_urls": "",
        }

    def clean(self) -> dict[str, Any]:
        super(CourtUploadForm, self).clean()
        self.validate_neutral_citation()
        self.make_panel()
        self.make_item_dict()
        self.verify_unique_judges()
        return self.cleaned_data

    def save(self) -> OpinionCluster:
        """Save uploaded Tennessee Workers Comp/Appeal to db.

        :return: Cluster
        """

        sha1_hash = sha1(force_bytes(self.cleaned_data.get("pdf_upload")))
        court = Court.objects.get(pk=self.cleaned_data.get("court_str"))

        docket, opinion, cluster, citations = make_objects(
            self.cleaned_data.get("item"),
            court,
            sha1_hash,
            self.cleaned_data.get("pdf_upload"),
        )

        if not citations:
            logger.warning("Citation not found for Tenn Workers' Forms")

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            },
            index=False,
        )

        extract_doc_content.delay(
            opinion.pk, ocr_available=True, citation_jitter=True
        )

        logging.info(
            "Successfully added Tennessee object cluster: %s", cluster.id
        )

        return cluster
