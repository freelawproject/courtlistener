import logging
from datetime import datetime
from django import forms

from cl.lib.crypto import sha1
from cl.people_db.models import Person
from cl.search.models import Court, Citation

from cl.search.fields import (
    CeilingDateField,
    FloorDateField,
)

from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content

from django.utils.encoding import force_bytes
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


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
    def __init__(self, *args, **kwargs):
        self.pk = kwargs.pop("pk", None)
        super(TennWorkersForm, self).__init__(*args, **kwargs)
        self.initial["court_str"] = self.pk

        q_judges = Person.objects.filter(positions__court_id=self.pk)
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
        widget=forms.Select(
            attrs={
                "class": "form-control",
                "placeholder": "Choose lead Author",
            }
        ),
    )

    second_judge = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Second panelist",
        widget=forms.Select(attrs={"class": "form-control",}),
    )

    third_judge = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Third panelist",
        widget=forms.Select(attrs={"class": "form-control",}),
    )

    cite_volume = forms.IntegerField(
        label="Cite year",
        required=True,
        widget=forms.Select(
            choices=[(x, x) for x in xrange(datetime.now().year, 2013, -1)],
            attrs={"class": "form-control"},
        ),
    )

    cite_reporter = forms.CharField(label="Cite reporter", required=True,)

    cite_page = forms.IntegerField(
        label="Cite page",
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

    def validate_neutral_citation(self):
        cv = self.cleaned_data.get("cite_volume")
        cr = self.cleaned_data.get("cite_reporter")
        cp = self.cleaned_data.get("cite_page")

        c = Citation.objects.filter(volume=cv, reporter=cr, page=cp).exists()
        if c:
            raise ValidationError("Citation already in system")
        self.cleaned_data["neutral_citation"] = "%s %s %s" % (cv, cr, cp)

    def clean_pdf_upload(self):
        return self.cleaned_data.get("pdf_upload").read()

    def make_panel(self):
        if self.pk == "tennworkcompapp":
            self.cleaned_data["panel"] = [
                self.cleaned_data.get("lead_author"),
                self.cleaned_data.get("second_judge"),
                self.cleaned_data.get("third_judge"),
            ]
        else:
            self.cleaned_data["panel"] = []

    def make_item_dict(self):
        self.cleaned_data["item"] = {
            "case_names": self.cleaned_data.get("case_title"),
            "case_dates": self.cleaned_data.get("publication_date"),
            "precedential_statuses": "Published",
            "docket_numbers": self.cleaned_data.get("docket_number"),
            "judges": ", ".join(
                [j.name_full for j in self.cleaned_data.get("panel")]
            ),
            "author_id": self.cleaned_data.get("lead_author").id,
            "author": self.cleaned_data.get("lead_author"),
            "date_filed_is_approximate": "False",
            "blocked_statuses": "False",
            "neutral_citations": self.cleaned_data.get("neutral_citation"),
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

        opinion.author = self.cleaned_data.get("lead_author")

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            },
            index=False,
        )

        for panel_judge in self.cleaned_data.get("panel"):
            cluster.panel.add(panel_judge)

        extract_doc_content.delay(
            opinion.pk, do_ocr=True, citation_jitter=True,
        )

        logging.info(
            "Successfully added Tennesee object cluster:%s", cluster.id
        )
        return cluster.id
