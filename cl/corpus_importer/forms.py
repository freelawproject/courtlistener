import typing
from typing import Any, Optional

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from cl.lib.forms import BootstrapModelForm
from cl.people_db.models import (
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    School,
    Source,
)
from cl.search.models import Court


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


class EmptyModelChoiceField(forms.ModelChoiceField):
    """Create a ModelChoiceField that allows the queryset to be set to empty.

    This is needed because if you set it to all(), it queries every item in
    the DB individually. That's pretty bad in general, but even if it just
    queried all the items in a single big query, that'd be unnecessary because
    this is meant to be used with an AJAX dropdown.

    When you use an AJAX dropdown, you don't need to query *any* of the items
    until the user does it on the front end.

    The main thing that needs to be done is allow the queryset to be set to
    XYZ.objects.none() by overriding the to_python method in ModelChoiceField.
    """

    @typing.no_type_check
    def to_python(self, value: Optional[Any]) -> Any:
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or "pk"
            if isinstance(value, self.queryset.model):
                value = getattr(value, key)
            # The next line is tweaked from:
            #    value = self.queryset.get(**{key: value})
            # The effect is to start with Model.objects.all() and query from
            # there. This won't work if you want a smaller queryset.
            value = self.queryset.model.objects.all().get(**{key: value})
        except (ValueError, TypeError, self.queryset.model.DoesNotExist):
            raise ValidationError(
                self.error_messages["invalid_choice"], code="invalid_choice"
            )
        return value


class EducationForm(BootstrapModelForm):
    school = EmptyModelChoiceField(
        queryset=School.objects.none(),
        widget=forms.Select(attrs={"class": "select2 school-select"}),
    )

    class Meta:
        model = Education
        exclude = ("id", "person")


EducationFormSet = inlineformset_factory(
    Person,
    Education,
    form=EducationForm,
    extra=3,
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
    court = EmptyModelChoiceField(
        queryset=Court.objects.none(),
        widget=forms.Select(attrs={"class": "select2 court-select"}),
    )
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
    extra=7,
)
