import re
from collections import OrderedDict

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ChoiceField, DateField
from django.utils.datastructures import MultiValueDictKeyError
from localflavor.us.us_states import STATE_CHOICES

from cl.lib.model_helpers import flatten_choices
from cl.people_db.models import PoliticalAffiliation, Position
from cl.search.fields import (
    CeilingDateField,
    FloorDateField,
    RandomChoiceField,
)
from cl.search.models import PRECEDENTIAL_STATUS, SEARCH_TYPES, Court

OPINION_ORDER_BY_CHOICES = (
    ("score desc", "Relevance"),
    ("dateFiled desc", "Newest First"),
    ("dateFiled asc", "Oldest First"),
    ("citeCount desc", "Most Cited First"),
    ("citeCount asc", "Least Cited First"),
    ("dateArgued desc", "Newest First"),
    ("dateArgued asc", "Oldest First"),
    ("entry_date_filed desc", "Newest Document First"),
    ("entry_date_filed asc", "Oldest Document First"),
    ("name_reverse asc", "Name"),
    ("dob desc,name_reverse asc", "Most Recently Born"),
    ("dob asc,name_reverse asc", "Least Recently Born"),
    ("dod desc,name_reverse asc", "Most Recently Deceased"),
)


def _clean_form(get_params, cd, courts):
    """Returns cleaned up values as a Form object."""
    # Send the user the cleaned up query
    get_params["q"] = cd["q"]

    # Clean up the date formats. This is probably no longer needed since we do
    # date cleanup on the client side via our datepickers, but it's probably
    # fine to leave it here until there's a reason to remove it. It could be
    # helpful if somebody finds a way not to use the datepickers (js off, say)
    for date_field in SearchForm().get_date_field_names():
        clean_up_date_formats(cd, date_field, get_params)
    get_params["order_by"] = cd["order_by"]
    get_params["type"] = cd["type"]

    for court in courts:
        get_params[f"court_{court.pk}"] = cd[f"court_{court.pk}"]

    for status in PRECEDENTIAL_STATUS.NAMES:
        get_params[f"stat_{status[1]}"] = cd[f"stat_{status[1]}"]

    # Ensure that we have the cleaned_data and other related attributes set.
    form = SearchForm(get_params)
    form.is_valid()
    return form


class SearchForm(forms.Form):
    #
    # Blended fields
    #
    type = forms.ChoiceField(
        choices=SEARCH_TYPES.NAMES,
        required=False,
        initial=SEARCH_TYPES.OPINION,
        widget=forms.RadioSelect(
            attrs={"class": "external-input form-control"}
        ),
    )
    type.as_str_types = []
    q = forms.CharField(required=False, label="Query")
    q.as_str_types = SEARCH_TYPES.ALL_TYPES
    court = forms.CharField(required=False, widget=forms.HiddenInput())
    court.as_str_types = []
    order_by = RandomChoiceField(
        choices=OPINION_ORDER_BY_CHOICES,
        required=False,
        label="Result Ordering",
        initial="score desc",
        widget=forms.Select(attrs={"class": "external-input form-control"}),
    )
    order_by.as_str_types = []

    #
    # Oral argument and Opinion shared fields
    #
    judge = forms.CharField(
        required=False,
        initial="",
        label="Judge",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    judge.as_str_types = [SEARCH_TYPES.OPINION, SEARCH_TYPES.ORAL_ARGUMENT]

    # Oral arg, opinion, and RECAP
    case_name = forms.CharField(
        required=False,
        label="Case Name",
        initial="",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    case_name.as_str_types = [
        SEARCH_TYPES.OPINION,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.ORAL_ARGUMENT,
    ]
    docket_number = forms.CharField(
        required=False,
        label="Docket Number",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    docket_number.as_str_types = [
        SEARCH_TYPES.OPINION,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.ORAL_ARGUMENT,
    ]

    #
    # RECAP fields
    #
    available_only = forms.BooleanField(
        label="Only show results with PDFs",
        label_suffix="",
        required=False,
        widget=forms.CheckboxInput(
            attrs={"class": "external-input form-control left"}
        ),
    )
    available_only.as_str_types = [SEARCH_TYPES.RECAP]
    description = forms.CharField(
        required=False,
        label="Document Description",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    description.as_str_types = [SEARCH_TYPES.RECAP]
    nature_of_suit = forms.CharField(
        required=False,
        label="Nature of Suit",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    nature_of_suit.as_str_types = [SEARCH_TYPES.RECAP]
    cause = forms.CharField(
        required=False,
        label="Cause",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    cause.as_str_types = [SEARCH_TYPES.RECAP]
    assigned_to = forms.CharField(
        required=False,
        label="Assigned To Judge",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    assigned_to.as_str_types = [SEARCH_TYPES.RECAP]
    referred_to = forms.CharField(
        required=False,
        label="Referred To Judge",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    referred_to.as_str_types = [SEARCH_TYPES.RECAP]
    document_number = forms.CharField(
        required=False,
        label="Document #",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    document_number.as_str_types = [SEARCH_TYPES.RECAP]
    attachment_number = forms.CharField(
        required=False,
        label="Attachment #",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    attachment_number.as_str_types = [SEARCH_TYPES.RECAP]
    party_name = forms.CharField(
        required=False,
        label="Party Name",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            },
        ),
    )
    party_name.as_str_types = [SEARCH_TYPES.RECAP]
    atty_name = forms.CharField(
        required=False,
        label="Attorney Name",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            },
        ),
    )
    atty_name.as_str_types = [SEARCH_TYPES.RECAP]

    #
    # Oral argument fields
    #
    argued_after = FloorDateField(
        required=False,
        label="Argued After",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    argued_after.as_str_types = [SEARCH_TYPES.ORAL_ARGUMENT]
    argued_before = CeilingDateField(
        required=False,
        label="Argued Before",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    argued_before.as_str_types = [SEARCH_TYPES.ORAL_ARGUMENT]

    #
    # Opinion fields
    #
    filed_after = FloorDateField(
        required=False,
        label="Filed After",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    filed_after.as_str_types = [SEARCH_TYPES.OPINION, SEARCH_TYPES.RECAP]
    filed_before = CeilingDateField(
        required=False,
        label="Filed Before",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    filed_before.as_str_types = [SEARCH_TYPES.OPINION, SEARCH_TYPES.RECAP]
    citation = forms.CharField(
        required=False,
        label="Citation",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    citation.as_str_types = [SEARCH_TYPES.OPINION]
    neutral_cite = forms.CharField(
        required=False,
        label="Neutral Citation",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    neutral_cite.as_str_types = [SEARCH_TYPES.OPINION]
    cited_gt = forms.IntegerField(
        required=False,
        label="Min Cites",
        initial=0,
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    cited_gt.as_str_types = [SEARCH_TYPES.OPINION]
    cited_lt = forms.IntegerField(
        required=False,
        label="Max Cites",
        initial=100000,
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    cited_lt.as_str_types = [SEARCH_TYPES.OPINION]

    #
    # Judge fields
    #
    name = forms.CharField(
        required=False,
        label="Name",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    name.as_str_types = [SEARCH_TYPES.PEOPLE]
    born_after = FloorDateField(
        required=False,
        label="Born After",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    born_after.as_str_types = [SEARCH_TYPES.PEOPLE]
    born_before = CeilingDateField(
        required=False,
        label="Born Before",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )
    born_before.as_str_types = [SEARCH_TYPES.PEOPLE]
    dob_city = forms.CharField(
        required=False,
        label="Birth City",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    dob_city.as_str_types = [SEARCH_TYPES.PEOPLE]
    dob_state = forms.ChoiceField(
        choices=[("", "---------")] + list(STATE_CHOICES),
        required=False,
        label="Birth State",
        widget=forms.Select(attrs={"class": "external-input form-control"}),
    )
    dob_state.as_str_types = [SEARCH_TYPES.PEOPLE]
    school = forms.CharField(
        required=False,
        label="School Attended",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    school.as_str_types = [SEARCH_TYPES.PEOPLE]
    appointer = forms.CharField(
        required=False,
        label="Appointed By",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )
    appointer.as_str_types = [SEARCH_TYPES.PEOPLE]
    selection_method = forms.ChoiceField(
        choices=[("", "---------")] + list(Position.SELECTION_METHODS),
        required=False,
        label="Selection Method",
        initial="None",
        widget=forms.Select(attrs={"class": "external-input form-control"}),
    )
    selection_method.as_str_types = [SEARCH_TYPES.PEOPLE]
    political_affiliation = forms.ChoiceField(
        choices=[("", "---------")]
        + list(PoliticalAffiliation.POLITICAL_PARTIES),
        required=False,
        label="Political Affiliation",
        initial="None",
        widget=forms.Select(attrs={"class": "external-input form-control"}),
    )
    political_affiliation.as_str_types = [SEARCH_TYPES.PEOPLE]

    def get_date_field_names(self):
        return {
            f_name.split("_")[0]
            for f_name, f in self.fields.items()
            if isinstance(f, DateField)
        }

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)
        """
        Normally we wouldn't need to use __init__ in a form object like
        this, however, since we are generating checkbox fields with dynamic
        names coming from the database, we need to interact directly with the
        fields dict.
        """
        courts = Court.objects.filter(in_use=True)
        for court in courts:
            self.fields[f"court_{court.pk}"] = forms.BooleanField(
                label=court.short_name,
                required=False,
                initial=True,
                widget=forms.CheckboxInput(attrs={"checked": "checked"}),
            )

        for status in PRECEDENTIAL_STATUS.NAMES:
            attrs = {}
            if status[1] == "Precedential":
                initial = True
                attrs.update({"checked": "checked"})
            else:
                initial = False
            new_field = forms.BooleanField(
                label=status[1],
                required=False,
                initial=initial,
                widget=forms.CheckboxInput(attrs=attrs),
            )
            new_field.as_str_types = [SEARCH_TYPES.OPINION]
            self.fields[f"stat_{status[1]}"] = new_field

    # This is a particularly nasty area of the code due to several factors:
    #  1. Django doesn't have a good method of setting default values for
    #     bound forms. As a result, we set them here as part of a cleanup
    #     routine. This way a user can do a query for page=2, and still have
    #     all the correct defaults.
    #  2. In our search form, part of what we do is clean up the GET requests
    #     that the user sent. This is completed in clean_form(). This allows a
    #     user to be taught what better queries look like. To do this, we have
    #     to make a temporary variable in _clean_form() and assign it
    #     the values of the cleaned_data. The upshot of this is that most
    #     changes made here will also need to be made in _clean_form().
    #     Failure to do that will result in the query being processed correctly
    #     (search results are all good), but the form on the UI won't be
    #     cleaned up for the user, making things rather confusing.
    #  3. We do some cleanup work in search_utils.make_stats_variable(). The
    #     work that's done there is used to check or un-check the boxes in the
    #     sidebar, so if you tweak how they work you'll need to tweak this
    #     function.
    # In short: This is a nasty area. Comments this long are a bad sign for
    # the intrepid developer.
    def clean_q(self):
        """
        Cleans up various problems with the query:
         - lowercase --> camelCase
         - '|' --> ' OR '
        """
        q = self.cleaned_data["q"]

        # Fix fields to work in all lowercase
        sub_pairs = (
            # Blended
            ("casename", "caseName"),
            ("case_name", "caseName"),
            ("docketnumber", "docketNumber"),
            ("datefiled", "dateFiled"),
            ("suitnature", "suitNature"),
            # Opinions
            ("lexiscite", "lexisCite"),
            ("neutralcite", "neutralCite"),
            ("citecount", "citeCount"),
            # Oral Args
            ("dateargued", "dateArgued"),
            ("datereargued", "dateReargued"),
            # People
            ("DOD", "dod"),
            ("DOB", "dob"),
            # RECAP
            ("dateterminated", "dateTerminated"),
            ("jurydemand", "juryDemand"),
        )
        for bad, good in sub_pairs:
            q = re.sub(bad, good, q)

        # Make pipes work
        q = re.sub(r"\|", " OR ", q)

        return q

    def clean_order_by(self):
        """Sets the default order_by value if one isn't provided by the
        user.
        """
        if not self.cleaned_data.get("type"):
            raise ValidationError("Invalid value for type field")

        if (
            self.cleaned_data["type"] == SEARCH_TYPES.OPINION
            or not self.cleaned_data["type"]
        ):
            if not self.cleaned_data["order_by"]:
                return self.fields["order_by"].initial
        elif self.cleaned_data["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
            if not self.cleaned_data["order_by"]:
                return "dateArgued desc"
        elif self.cleaned_data["type"] == SEARCH_TYPES.PEOPLE:
            if not self.cleaned_data["order_by"]:
                return "name_reverse asc"
        return self.cleaned_data["order_by"]

    def clean_type(self):
        """Make sure that type has an initial value."""
        if not self.cleaned_data["type"]:
            return self.fields["type"].initial
        return self.cleaned_data["type"]

    def clean(self):
        """
        Handles validation fixes that need to be performed across fields.
        """
        cleaned_data = self.cleaned_data

        # 1. Make sure that the dates do this |--> <--| rather than <--| |-->
        for field_name in self.get_date_field_names():
            before = cleaned_data.get(f"{field_name}_before")
            after = cleaned_data.get(f"{field_name}_after")
            if before and after and (before < after):
                # The user is requesting dates like this: <--b  a-->. Switch
                # the dates so their query is like this: a-->   <--b
                cleaned_data[f"{field_name}_before"] = after
                cleaned_data[f"{field_name}_after"] = before

        # 2. Convert the value in the court field to the various court_* fields
        court_str = cleaned_data.get("court")
        if court_str:
            if " " in court_str:
                court_ids = court_str.split(" ")
            elif "," in court_str:
                court_ids = court_str.split(",")
            else:
                court_ids = [court_str]
            for court_id in court_ids:
                cleaned_data[f"court_{court_id}"] = True

        # 3. Make sure that the user has selected at least one facet for each
        #    taxonomy. Note that this logic must be paralleled in
        #    search_utils.make_facet_variable
        court_bools = [
            v for k, v in cleaned_data.items() if k.startswith("court_")
        ]
        if not any(court_bools):
            # Set all facets to True
            for key in cleaned_data.keys():
                if key.startswith("court_"):
                    cleaned_data[key] = True

        stat_bools = [
            v for k, v in cleaned_data.items() if k.startswith("stat_")
        ]
        if not any(stat_bools):
            # Set everything to False...
            for key in cleaned_data.keys():
                if key.startswith("stat_"):
                    cleaned_data[key] = False
            # ...except precedential
            cleaned_data["stat_Precedential"] = True

        cleaned_data["_court_count"] = len(court_bools)
        cleaned_data["_stat_count"] = len(stat_bools)

        # 4. Strip any whitespace, otherwise it crashes Solr.
        for k, v in cleaned_data.items():
            if isinstance(v, str):
                cleaned_data[k] = v.strip()

        return cleaned_data

    def as_display_dict(self, court_count_human):
        """Generate a displayable dictionary of the search form

        This can be useful for displaying on the front end, or converting into
        a useful string. The dictionary looks like:

            {
              'Case name': 'Foo',
              'Query': 'bar',
            }

        :param court_count_human: The number of courts being queried or "All",
        if all courts are being queried.
        :returns A dictionary of the data
        """
        # The search type is usually provided by cleaned data, but can be
        # missing when the form is invalid (and lacks it). If so, just give up.
        try:
            search_type = self.data["type"]
        except MultiValueDictKeyError:
            return {}
        display_dict = OrderedDict({"Courts": court_count_human})
        for field_name, field in self.fields.items():
            if not hasattr(field, "as_str_types"):
                continue
            if search_type in field.as_str_types:
                value = self.cleaned_data.get(field_name)
                if value:
                    if isinstance(field, ChoiceField):
                        choices = flatten_choices(self.fields[field_name])
                        value = dict(choices)[value]
                    display_dict[field.label] = value

        return display_dict

    def as_text(self, court_count_human):
        """Create a human-readable string representation of the search form"""
        crumbs = []
        for label, value in self.as_display_dict(court_count_human).items():
            crumbs.append(f"{label}: {value}")
        return " › ".join(crumbs)


class ParentheticalSearchForm(forms.Form):
    ORDER_BY_OPTIONS = []

    q = forms.CharField(required=False, label="Query")

    order_by = forms.ChoiceField(
        label="Search Results Order:",
        required=False,
        initial="-score",
        choices=ORDER_BY_OPTIONS,
        widget=forms.Select(attrs={"class": "external-input form-control"}),
    )

    filed_after = FloorDateField(
        required=False,
        label="Filed After",
        widget=forms.TextInput(
            attrs={
                "placeholder": "MM/DD/YYYY",
                "class": "external-input form-control datepicker",
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
                "class": "external-input form-control datepicker",
                "autocomplete": "off",
            }
        ),
    )

    court = forms.CharField(required=False, widget=forms.HiddenInput())
    court.as_str_types = []

    docket_number = forms.CharField(
        required=False,
        label="Docket Number",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )

    opinion_id = forms.CharField(
        required=False,
        label="Opinion id",
        widget=forms.TextInput(
            attrs={
                "class": "external-input form-control",
                "autocomplete": "off",
            }
        ),
    )

    def get_date_field_names(self):
        return {
            f_name.split("_")[0]
            for f_name, f in self.fields.items()
            if isinstance(f, DateField)
        }

    def __init__(self, *args, **kwargs):
        search_type = kwargs.pop("search_type", None)
        super(ParentheticalSearchForm, self).__init__(*args, **kwargs)
        """
        Normally we wouldn't need to use __init__ in a form object like
        this, however, since we are generating checkbox fields with dynamic
        names coming from the database, we need to interact directly with the
        fields dict.
        """

        # Clear options to avoid duplicates
        self.ORDER_BY_OPTIONS.clear()
        courts = Court.objects.filter(in_use=True)
        for court in courts:
            self.fields[f"court_{court.pk}"] = forms.BooleanField(
                label=court.short_name,
                required=False,
                initial=True,
                widget=forms.CheckboxInput(attrs={"checked": "checked"}),
            )

        # Add options based on search type
        if search_type == "parenthetical":
            self.ORDER_BY_OPTIONS.append(("score desc", "Relevance"))
            self.ORDER_BY_OPTIONS.append(("dateFiled desc", "Newest First"))
            self.ORDER_BY_OPTIONS.append(("dateFiled asc", "Oldest First"))

        self.fields["order_by"].choices = self.ORDER_BY_OPTIONS

    def clean(self):
        """
        Handles validation fixes that need to be performed across fields.
        """
        cleaned_data = self.cleaned_data

        # 1. Make sure that the dates do this |--> <--| rather than <--| |-->
        for field_name in self.get_date_field_names():
            before = cleaned_data.get(f"{field_name}_before")
            after = cleaned_data.get(f"{field_name}_after")
            if before and after and (before < after):
                # The user is requesting dates like this: <--b  a-->. Switch
                # the dates so their query is like this: a-->   <--b
                cleaned_data[f"{field_name}_before"] = after
                cleaned_data[f"{field_name}_after"] = before

        # 2. Convert the value in the court field to the various court_* fields
        court_str = cleaned_data.get("court")
        if court_str:
            if " " in court_str:
                court_ids = court_str.split(" ")
            elif "," in court_str:
                court_ids = court_str.split(",")
            else:
                court_ids = [court_str]
            for court_id in court_ids:
                cleaned_data[f"court_{court_id}"] = True

        # 3. Make sure that the user has selected at least one facet for each
        #    taxonomy.
        court_bools = [
            v for k, v in cleaned_data.items() if k.startswith("court_")
        ]
        if not any(court_bools):
            # Set all facets to True
            for key in cleaned_data.keys():
                if key.startswith("court_"):
                    cleaned_data[key] = True

        cleaned_data["_court_count"] = len(court_bools)

        # 4. Strip any whitespace, otherwise it crashes Solr.
        for k, v in cleaned_data.items():
            if isinstance(v, str):
                cleaned_data[k] = v.strip()

        return cleaned_data

    def as_display_dict(self, court_count_human):
        """Generate a displayable dictionary of the search form

        This can be useful for displaying on the front end, or converting into
        a useful string. The dictionary looks like:

            {
              'Case name': 'Foo',
              'Query': 'bar',
            }

        :param court_count_human: The number of courts being queried or "All",
        if all courts are being queried.
        :returns A dictionary of the data
        """

        display_dict = OrderedDict({"Courts": court_count_human})
        for field_name, field in self.fields.items():
            if not hasattr(field, "as_str_types"):
                continue
            value = self.cleaned_data.get(field_name)
            if value:
                if isinstance(field, ChoiceField):
                    choices = flatten_choices(self.fields[field_name])
                    value = dict(choices)[value]
                display_dict[field.label] = value

        return display_dict

    def as_text(self, court_count_human):
        """Create a human-readable string representation of the search form"""
        crumbs = []
        for label, value in self.as_display_dict(court_count_human).items():
            if label:
                crumbs.append(f"{label}: {value}")
        return " › ".join(crumbs)


def _clean_es_form(get_params, cd, courts, search_type, formclass):
    """Returns cleaned up values as a Form object."""
    # Send the user the cleaned up query
    get_params["q"] = cd["q"]

    # Clean up the date formats. This is probably no longer needed since we do
    # date cleanup on the client side via our datepickers, but it's probably
    # fine to leave it here until there's a reason to remove it. It could be
    # helpful if somebody finds a way not to use the datepickers (js off, say)
    for date_field in ParentheticalSearchForm().get_date_field_names():
        clean_up_date_formats(cd, date_field, get_params)

    get_params["order_by"] = cd["order_by"]
    for court in courts:
        get_params[f"court_{court.pk}"] = cd[f"court_{court.pk}"]

    form = formclass(get_params, search_type=search_type)
    form.is_valid()
    return form


def clean_up_date_formats(
    cd: dict[str, any], date_field: str, get_params: dict[str, any]
) -> None:
    """Clean up date formats in a given params dictionary.

    :param cd: The cleaned data dict.
    :param date_field: The name of the date field to be cleaned up.
    :param get_params: The query request params.
    :return: None
    """

    for time in ("before", "after"):
        field = f"{date_field}_{time}"
        if get_params.get(field) and cd.get(field) is not None:
            # Don't use strftime. It'll fail before 1900
            before = cd[field]
            get_params[field] = "%02d/%02d/%s" % (
                before.month,
                before.day,
                before.year,
            )
