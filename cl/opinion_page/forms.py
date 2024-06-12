import logging
from datetime import datetime
from typing import Any, MutableMapping

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, URLValidator
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.encoding import force_bytes
from django.utils.html import format_html
from juriscraper.lib.string_utils import titlecase

from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.people_db.lookup_utils import extract_judge_last_name
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
    OriginatingCourtInformation,
)
from cl.users.models import UserProfile


class CitationRedirectorForm(forms.Form):
    volume = forms.IntegerField(
        widget=forms.TextInput(
            attrs={"class": "form-control input-lg", "placeholder": "Volume"}
        ),
        required=False,
    )
    # We change the placeholder to allow people to continue to use the rest
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
        super().__init__(*args, **kwargs)

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


class BaseCourtUploadForm(forms.Form):
    """Base form to be used with court uploads

    Here we define the minimum required fields and some methods to add extra fields,
    in case of require something special those can be redefined on each court form.
    """

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
    download_url = forms.URLField(
        validators=[URLValidator()],
        label="Download Url",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "The URL where the document is originally located",
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
        super().__init__(*args, **kwargs)
        self.initial["court_str"] = self.pk
        self.initial["court"] = Court.objects.get(pk=self.pk)

    def add_author_field(self, required=True):
        """Add author field to form

        :param required: field is required or not
        :return: None
        """
        lead_author = forms.ModelChoiceField(
            queryset=Person.objects.none(),
            required=required,
            label="Lead Author",
            widget=forms.Select(
                attrs={
                    "class": "form-control",
                    "placeholder": "Choose Lead Author",
                }
            ),
        )
        self.fields["lead_author"] = lead_author

    def add_author_str_field(self, required=True):
        """Add author str field to form

        :param required: field is required or not
        :return: None
        """
        author_str = forms.CharField(
            label="Author String",
            required=required,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Use this in case you can't find the name in the "
                    "list above",
                    "autocomplete": "off",
                }
            ),
        )
        self.fields["author_str"] = author_str

    def add_judges_field(self, required=True):
        """Add judges field to form

        :param required: field is required or not
        :return: None
        """
        judges = forms.CharField(
            label="Judges",
            required=required,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Judges",
                    "autocomplete": "off",
                }
            ),
        )
        self.fields["judges"] = judges

    def add_panel_field(self, required=True):
        """Add panel field to form

        :param required: field is required or not
        :return: None
        """
        panel = forms.ModelMultipleChoiceField(
            queryset=Person.objects.none(),
            required=required,
            label="Panel",
            widget=forms.SelectMultiple(
                attrs={
                    "class": "form-control input-lg",
                    "height": "100%",
                    "size": "10",
                }
            ),
        )
        self.fields["panel"] = panel

    def add_argue_fields(self, required=True):
        """Add argued/reargued field to form

        :param required: field is required or not
        :return: None
        """
        date_argued = forms.DateField(
            label="Argued Date",
            required=required,
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
            required=required,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control datepicker",
                    "placeholder": "Reargued Date",
                    "autocomplete": "off",
                }
            ),
        )
        self.fields["date_argued"] = date_argued
        self.fields["date_reargued"] = date_reargued

    def add_citation_fields(self, required=True) -> None:
        """Add citations fields to form

        :param required: field is required or not
        :return: None
        """
        cite_volume = forms.IntegerField(
            label="Cite Year",
            required=required,
            widget=forms.Select(
                choices=[(x, x) for x in range(datetime.now().year, 2013, -1)],
                attrs={"class": "form-control"},
            ),
        )
        cite_reporter = forms.CharField(
            label="Cite Reporter",
            required=required,
        )
        cite_page = forms.IntegerField(
            label="Cite Page",
            required=required,
            widget=forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "off",
                }
            ),
        )

        self.fields["cite_volume"] = cite_volume
        self.fields["cite_reporter"] = cite_reporter
        self.fields["cite_page"] = cite_page

    @staticmethod
    def person_label(obj) -> str:
        """Get person full name

        :param obj: Person object
        :return: person full name
        """
        return obj.name_full

    def make_panel(self) -> None:
        """Build panel from lead_author and panel field

        :return: None
        """
        if not self.cleaned_data.get("panel") and self.cleaned_data.get(
            "lead_author"
        ):
            # No panel field or no panel field data, use lead author
            self.cleaned_data["panel"] = [self.cleaned_data["lead_author"]]
        else:
            self.cleaned_data["panel"] = self.cleaned_data.get("panel", [])

    def get_judges_qs(self):
        """Get judges from specific court

        :return: list of judges from specific court
        """
        return Person.objects.filter(
            positions__court_id=self.pk,
            is_alias_of=None,
            positions__date_retirement=None,
        ).order_by("name_first")

    def set_judges_qs(self) -> None:
        """Set Person queryset for panel/judge fields

        :return: None
        """
        judges_qs = self.get_judges_qs()

        for field_name in [
            "lead_author",
            "second_judge",
            "third_judge",
            "panel",
        ]:
            if field_name in self.fields:
                self.fields[
                    field_name
                ].queryset = judges_qs  # type: ignore[attr-defined]
                self.fields[
                    field_name
                ].label_from_instance = self.person_label  # type: ignore[attr-defined]

    def validate_neutral_citation(self) -> None:
        """Validate if we already have the neutral citation in the system

        :return: None
        """
        volume = self.cleaned_data.get("cite_volume")
        reporter = self.cleaned_data.get("cite_reporter")
        page = self.cleaned_data.get("cite_page")

        if volume and reporter and page:
            c = Citation.objects.filter(
                volume=volume, reporter=reporter, page=page
            )
            if c.exists():
                cite = c.first()
                self.add_error(
                    "cite_page",
                    ValidationError(
                        format_html(
                            'Citation already in database. See: <a href="%s">%s</a>'
                            % (
                                cite.get_absolute_url(),
                                cite.cluster.case_name,
                            ),
                        )
                    ),
                )
            self.cleaned_data["citations"] = f"{volume} {reporter} {page}"

    def clean_pdf_upload(self) -> bytes:
        """Check if we already have the pdf in the system

        :return: pdf data
        """
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

    def make_item_dict(self) -> None:
        """Make item dictionary for adding to our DB

        :return: None
        """
        lead_author = self.cleaned_data.get("lead_author")

        judges_list = [
            j.name_full for j in self.cleaned_data.get("panel", []) if j
        ]
        if self.cleaned_data.get("judges"):
            # We can have additional judges from char field that are not in the system
            judges_list.append(self.cleaned_data.get("judges"))

        judges_str = ", ".join(list(set(judges_list)))
        nomalized_judges = titlecase(
            ", ".join(extract_judge_last_name(judges_str))
        )

        self.cleaned_data["item"] = {
            "source": Docket.DIRECT_INPUT,
            "cluster_source": SOURCES.DIRECT_COURT_INPUT,
            "disposition": self.cleaned_data.get("disposition", ""),
            "case_names": self.cleaned_data.get("case_title"),
            "case_dates": self.cleaned_data.get("publication_date"),
            "precedential_statuses": "Published",
            "docket_numbers": self.cleaned_data.get("docket_number"),
            "judges": nomalized_judges,
            "author_id": lead_author.id if lead_author else None,
            "author": lead_author,
            "date_filed_is_approximate": False,
            "blocked_statuses": False,
            "citations": self.cleaned_data.get("citations", ""),
            "summary": self.cleaned_data.get("summary", ""),
            "download_urls": self.cleaned_data.get("download_url", ""),
            "author_str": self.cleaned_data.get("author_str", ""),
        }

    def save(self) -> OpinionCluster:
        """Save court decision data to db.

        :return: Cluster
        """

        self.make_panel()
        self.make_item_dict()

        sha1_hash = sha1(force_bytes(self.cleaned_data.get("pdf_upload")))
        court = Court.objects.get(pk=self.cleaned_data.get("court_str"))

        docket, opinion, cluster, citations = make_objects(
            self.cleaned_data.get("item"),
            court,
            sha1_hash,
            self.cleaned_data.get("pdf_upload"),
        )

        if not citations:
            logger.warning(
                f"Citation not found for court id: {self.cleaned_data.get('court_str')} form"
            )

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            },
            index=False,
        )

        if self.cleaned_data.get("lower_court_docket_number"):
            originating_court = OriginatingCourtInformation.objects.create(
                docket_number=self.cleaned_data.get(
                    "lower_court_docket_number"
                )
            )
            docket.originating_court_information = originating_court
            docket.save()

        extract_doc_content.delay(
            opinion.pk, ocr_available=True, citation_jitter=True
        )

        logging.info(
            f"Successfully added object cluster: {cluster.id} for {self.cleaned_data.get('court_str')}"
        )

        return cluster


class MeCourtUploadForm(BaseCourtUploadForm):
    """
    Form for Supreme Judicial Court of Maine (me) Upload Portal
    """

    def get_judges_qs(self):
        return (
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
                    When(positions__position_type="ass-jus", then=Value(2)),
                    When(
                        positions__position_type="ret-act-jus",
                        then=Value(3),
                    ),
                    output_field=IntegerField(),
                )
            )
            .order_by("custom_order", "positions__date_start")
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Add required fields for specific court
        self.add_citation_fields()
        self.add_argue_fields(required=False)
        self.add_panel_field()

        # The court requested the order of the panel match the seniority
        # of the judges, in order or date joined after sorting by pos type
        # Chief, Associate, Retired Active
        # Additionally, we only want active justices so remove them if
        # terminated or retired, without a new role being created as a
        # retired active justice
        self.set_judges_qs()

        self.fields["cite_reporter"].widget = forms.Select(
            choices=[("ME", "ME")],
            attrs={"class": "form-control", "readonly": "readonly"},
        )

        self.order_fields(
            [
                "case_title",
                "docket_number",
                "publication_date",
                "date_argued",
                "date_reargued",
                "panel",
                "cite_volume",
                "cite_reporter",
                "cite_page",
                "download_url",
                "pdf_upload",
            ]
        )

    def clean(self) -> dict[str, Any]:
        super().clean()
        self.validate_neutral_citation()
        return self.cleaned_data


class TennWorkCompClUploadForm(BaseCourtUploadForm):
    """
    Form for Tennessee Court of Workers' Compensation Claims (tennworkcompcl) Upload
    Portal
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_author_field()
        self.set_judges_qs()
        self.add_citation_fields()

        self.fields["cite_reporter"].widget = forms.Select(
            choices=[("TN WC", "TN WC")],
            attrs={"class": "form-control", "readonly": "readonly"},
        )

        self.order_fields(
            [
                "case_title",
                "docket_number",
                "publication_date",
                "lead_author",
                "cite_volume",
                "cite_reporter",
                "cite_page",
                "download_url",
                "pdf_upload",
            ]
        )

    def clean(self) -> dict[str, Any]:
        super().clean()
        self.validate_neutral_citation()
        return self.cleaned_data


class TennWorkCompAppUploadForm(BaseCourtUploadForm):
    """
    Form for Tennessee Workers' Compensation Appeals Board (tennworkcompapp) Upload
    Portal
    """

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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_author_field()
        self.set_judges_qs()
        self.add_citation_fields()

        self.fields["cite_reporter"].widget = forms.Select(
            choices=[("TN WC App.", "TN WC App.")],
            attrs={"class": "form-control", "readonly": "readonly"},
        )

        self.order_fields(
            [
                "case_title",
                "docket_number",
                "publication_date",
                "lead_author",
                "second_judge",
                "third_judge",
                "cite_volume",
                "cite_reporter",
                "cite_page",
                "download_url",
                "pdf_upload",
            ]
        )

    def verify_unique_judges(self) -> None:
        judges = [
            self.cleaned_data["lead_author"],
            self.cleaned_data["second_judge"],
            self.cleaned_data["third_judge"],
        ]
        # Remove None when judges are optional
        judges = [judge for judge in judges if judge is not None]
        flag = len(set(judges)) == len(judges)
        if not flag:
            self.add_error(
                "lead_author",
                ValidationError("Please select each judge only once."),
            )

    def make_panel(self) -> None:
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

    def clean(self) -> dict[str, Any]:
        super().clean()
        # Special validation for compartmental
        self.verify_unique_judges()
        self.validate_neutral_citation()
        return self.cleaned_data


class MoCourtUploadForm(BaseCourtUploadForm):
    """
    Form for Missouri Upload Portal (mo, moctapped, moctappsd and moctappwd)
    """

    disposition = forms.CharField(
        label="Disposition",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
            }
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_author_field()
        self.add_judges_field()
        self.set_judges_qs()
        self.add_author_str_field(required=False)
        self.order_fields(
            [
                "case_title",
                "docket_number",
                "publication_date",
                "lead_author",
                "author_str",
                "judges",
                "disposition",
                "download_url",
                "pdf_upload",
            ]
        )


class MissCourtUploadForm(BaseCourtUploadForm):
    """
    Form for Mississippi Upload Portal (miss and missctapp)
    """

    disposition = forms.CharField(
        label="Disposition",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
            }
        ),
    )

    summary = forms.CharField(
        label="Summary",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_author_field()
        self.set_judges_qs()
        self.add_judges_field()
        self.add_author_str_field(required=False)
        self.order_fields(
            [
                "case_title",
                "docket_number",
                "publication_date",
                "lead_author",
                "author_str",
                "judges",
                "disposition",
                "summary",
                "download_url",
                "pdf_upload",
            ]
        )
