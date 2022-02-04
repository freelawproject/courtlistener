from django import forms
from django.forms import inlineformset_factory

from cl.lib.forms import BootstrapModelForm
from cl.people_db.models import (
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    Source,
)


class PersonFilterForm(forms.Form):
    name = forms.CharField(
        label="Judge name",
        required=False,
    )
    court = forms.CharField(
        label="Court ID",
        required=False,
    )
    court_type = forms.CharField(
        label="Court type",
        required=False,
    )


class RaceModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Race) -> str:
        return obj.get_race_display()


class PersonForm(BootstrapModelForm):
    race = RaceModelMultipleChoiceField(
        queryset=Race.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": "6"}),
    )
    date_dob = forms.DateField(
        label="Date of Birth",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "datepicker",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = Person
        fields = [
            "name_first",
            "name_middle",
            "name_last",
            "name_suffix",
            "date_dob",
            "date_granularity_dob",
            "dob_city",
            "dob_state",
            "gender",
            "race",
            "religion",
        ]


class EducationForm(BootstrapModelForm):
    class Meta:
        model = Education
        exclude = ("id", "person")


EducationFormSet = inlineformset_factory(
    Person,
    Education,
    form=EducationForm,
    extra=3,
    widgets={
        "school": forms.TextInput(),
    },
)


class PoliticalAffiliationForm(BootstrapModelForm):
    date_start = forms.DateField(
        label="Date start",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "datepicker",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = PoliticalAffiliation
        exclude = ("id", "person", "date_end", "date_granularity_end")


PoliticalAffiliationFormSet = inlineformset_factory(
    Person,
    PoliticalAffiliation,
    form=PoliticalAffiliationForm,
    extra=2,
)


class PositionForm(BootstrapModelForm):
    date_start = forms.DateField(
        label="Date started",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "datepicker",
                "autocomplete": "off",
            }
        ),
    )
    date_termination = forms.DateField(
        label="Date terminated",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "datepicker",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = Position
        exclude = ("id", "person")
        fields = (
            "position_type",
            "court",
            "date_start",
            "date_granularity_start",
            "date_termination",
            "date_granularity_termination",
        )


PositionsFormSet = inlineformset_factory(
    Person,
    Position,
    fk_name="person",
    form=PositionForm,
    extra=2,
)


class SourceForm(BootstrapModelForm):
    date_accessed = forms.DateField(
        label="Date accessed",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "datepicker",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = Source
        exclude = ("id", "person")


SourcesFormSet = inlineformset_factory(
    Person,
    Source,
    form=SourceForm,
    extra=2,
)
