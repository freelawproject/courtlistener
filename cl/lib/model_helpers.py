import contextlib
import os
import re
from typing import Callable, Optional

from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename, slugify
from django.utils.timezone import now

from cl.custom_filters.templatetags.text_filters import oxford_join
from cl.lib.recap_utils import get_bucket_name
from cl.lib.string_utils import normalize_dashes, trunc

dist_d_num_regex = r"(?:\d:)?(\d\d)-..-(\d+)"
appellate_bankr_d_num_regex = r"(\d\d)-(\d+)"


def is_docket_number(value: str) -> bool:
    pattern = rf"{dist_d_num_regex}|{appellate_bankr_d_num_regex}"
    if re.match(pattern, value):
        return True
    return False


def clean_docket_number(docket_number: str | None) -> str:
    """Clean a docket number and returns the actual docket_number if is a
    valid docket number and if there is only one valid docket number.

    Converts docket numbers like:

    CIVIL ACTION NO. 7:17-CV-00426 -> 7:17-CV-00426
    4:20-cv-01245 -> 4:20-cv-01245
    No. 17-1142 -> 17-1142
    17-1142 -> 17-1142
    Nos. C 123-80-123-82 -> "" no valid docket number
    Nos. 212-213 -> "" no valid docket number
    Nos. 17-11426, 15-11166 -> "" multiple valid docket numbers

    :param docket_number: The docket number to clean.
    :return: The cleaned docket number or an empty string if no valid docket
    number is found.
    """
    if docket_number is None:
        return ""

    # Normalize dashes
    docket_number = normalize_dashes(docket_number)
    # Normalize to lowercase
    docket_number = docket_number.lower()
    # Match all the valid district docket numbers in a string.
    district_m = re.findall(r"\b(?:\d:)?\d\d-..-\d+", docket_number)
    if len(district_m) == 1:
        return district_m[0]

    # Match all the valid bankruptcy and appellate docket numbers at the
    # beginning of a string, after a blank space or after a comma.
    bankr_m = re.findall(r"(?<![^ ,])\d\d-\d+", docket_number)
    if len(bankr_m) == 1:
        return bankr_m[0]

    return ""


def make_docket_number_core(docket_number: Optional[str]) -> str:
    """Make a core docket number from an existing docket number.

    Converts docket numbers like:

        2:12-cv-01032
        12-cv-01032
        12-332

    Into:

        1201032

    Changes here should be reflected in the RECAP extension's
    makeDocketNumberCore function.

    :param docket_number: A docket number to condense
    :return empty string if no change possible, or the condensed version if it
    worked. Note that all values returned are strings. We cannot return an int
    because that'd strip leading zeroes, which we need.
    """
    if docket_number is None:
        return ""

    cleaned_docket_number = clean_docket_number(docket_number)

    district_m = re.search(dist_d_num_regex, cleaned_docket_number)
    if district_m:
        return f"{district_m.group(1)}{int(district_m.group(2)):05d}"

    bankr_m = re.search(appellate_bankr_d_num_regex, cleaned_docket_number)
    if bankr_m:
        # Pad to six characters because some courts have a LOT of bankruptcies
        return f"{bankr_m.group(1)}{int(bankr_m.group(2)):06d}"

    return ""


def make_path(root: str, filename: str) -> str:
    """Make a simple path for uploaded files.

    Start with the `root` node, and use the current date as the subdirectories.
    """
    d = now()
    return os.path.join(
        root, f"{d.year}", "%02d" % d.month, "%02d" % d.day, filename
    )


def make_lasc_path(instance, filename):
    """Make a simple path for uploaded files.

    Start with the `root` node, and use the current date as the subdirectories.
    """
    return os.path.join(
        "lasc-data", f"{instance.sha1[0:2]}", f"{instance.sha1[2:]}.json"
    )


def make_recap_path(instance, filename):
    """Make a path to a good location on the local system for RECAP files.

    This dumps them all into the same directory, which seems to be OK, at least
    so far.
    """
    return f"recap/{get_valid_filename(filename)}"


def base_recap_path(instance, filename, base_dir):
    """Make a filepath, accepting an extra parameter for the base directory

    Mirrors technique used by original RECAP server to upload PDFs to IA.
    """
    return os.path.join(
        base_dir,
        get_bucket_name(
            instance.docket_entry.docket.court_id,
            instance.docket_entry.docket.pacer_case_id,
        ),
        filename,
    )


def make_pdf_path(instance, filename, thumbs=False):
    from cl.lasc.models import LASCPDF
    from cl.search.models import ClaimHistory, RECAPDocument

    if type(instance) == RECAPDocument:
        root = "recap"
        court_id = instance.docket_entry.docket.court_id
        pacer_case_id = instance.docket_entry.docket.pacer_case_id
    elif type(instance) == ClaimHistory:
        root = "claim"
        court_id = instance.claim.docket.court_id
        pacer_case_id = instance.pacer_case_id
    elif type(instance) == LASCPDF:
        slug = slugify(trunc(filename, 40))
        root = f"/us/state/ca/lasc/{instance.docket_number}/"
        file_name = "gov.ca.lasc.%s.%s.%s.pdf" % (
            instance.docket_number,
            instance.document_id,
            slug,
        )

        return os.path.join(root, file_name)
    else:
        raise ValueError(
            f"Unknown model type in make_pdf_path function: {type(instance)}"
        )

    if thumbs:
        root = f"{root}-thumbnails"
    return os.path.join(
        root, get_bucket_name(court_id, pacer_case_id), filename
    )


def make_json_path(instance, filename):
    # As additional types are needed, this will need to mirror the format of
    # make_pdf_path, by doing type checking.
    return make_path("json-data", filename)


def make_lasc_json_path(instance, filename):
    # As additional types are needed, this will need to mirror the format of
    # make_pdf_path, by doing type checking.
    return make_lasc_path(instance, filename)


def make_pdf_thumb_path(instance, filename):
    return make_pdf_path(instance, filename, thumbs=True)


def make_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf

    This function requires that when you save an item you provide an attribute
    called file_with_date on the object. That date will be used to place the
    item in the correct location on disk.
    """
    try:
        # Cannot do proper type checking here because of circular import
        # problems when importing Audio, Document, etc.
        d = instance.file_with_date
    except AttributeError:
        from cl.audio.models import Audio
        from cl.search.models import Opinion, OpinionCluster

        if type(instance) == Audio:
            d = instance.docket.date_argued
        elif type(instance) == Opinion:
            d = instance.cluster.date_filed
        elif type(instance) == OpinionCluster:
            d = instance.date_filed

    return "%s/%s/%02d/%02d/%s" % (
        filename.split(".")[-1],
        d.year,
        d.month,
        d.day,
        get_valid_filename(filename),
    )


def validate_partial_date(instance, fields):
    """Ensure that partial dates make sense.

    Validates that:
     - Both granularity and date field are either completed or empty (one cannot
       be completed if the other is not).
     - If a partial date, the day/month is/are set to 01.
    """
    from cl.people_db.models import GRANULARITY_MONTH, GRANULARITY_YEAR

    for field in fields:
        d = getattr(instance, f"date_{field}")
        granularity = getattr(instance, f"date_granularity_{field}")

        if any([d, granularity]) and not all([d, granularity]):
            raise ValidationError(
                {
                    f"date_{field}": "Date and granularity must both be complete "
                    "or blank. Hint: The values are: date: %s, "
                    "granularity: %s" % (d, granularity)
                }
            )

        # If a partial date, are days/month set to 1?
        bad_date = False
        if granularity == GRANULARITY_YEAR:
            if d.month != 1 and d.day != 1:
                bad_date = True
        if granularity == GRANULARITY_MONTH:
            if d.day != 1:
                bad_date = True
        if bad_date:
            raise ValidationError(
                {
                    f"date_{field}": "Granularity was set as partial, but date "
                    "appears to include month/day other than 1."
                }
            )


def validate_is_not_alias(instance, fields):
    """Ensure that an alias to an object is not being used instead of the object
    itself.

    Requires that the object have an is_alias property or attribute.
    """
    for field in fields:
        referenced_object = getattr(instance, field)
        if referenced_object is not None and referenced_object.is_alias:
            raise ValidationError(
                {
                    field: 'Cannot set "%s" field to an alias of a "%s". Hint: '
                    '"%s" is an alias of "%s"'
                    % (
                        field,
                        type(referenced_object).__name__,
                        referenced_object,
                        referenced_object.is_alias_of,
                    )
                }
            )


def validate_has_full_name(instance):
    """This ensures that blank values are not passed to the first and last name
    fields. Normally this can be done by the DB layer, but people could still
    pass blank strings through, and this blocks even that.
    """
    if not all([instance.name_first, instance.name_last]):
        raise ValidationError("Both first and last names are required.")


def validate_nomination_fields_ok(instance):
    """Validate a few things:
    - date_nominated and date_elected cannot both have values
    - if nominated, then date_elected not complete and vice versa.
    """
    if instance.date_nominated and instance.date_elected:
        raise ValidationError(
            "Cannot have both a date nominated and a date elected."
        )

    if instance.how_selected:
        selection_type_group = instance.SELECTION_METHOD_GROUPS[
            instance.how_selected
        ]
        if selection_type_group == "Election" and instance.date_nominated:
            raise ValidationError(
                "Cannot have a nomination date for a position with how_selected of "
                "%s" % instance.get_how_selected_display()
            )
        if selection_type_group == "Appointment" and instance.date_elected:
            raise ValidationError(
                "Cannot have an election date for a position with how_selected of "
                "%s" % instance.get_how_selected_display()
            )


def validate_supervisor(instance):
    """Ensure that the supervisor field makes sense.

    - Supervisors can only be judges.
    - Supervisor field can only be completed when the position is that of a
      clerk.
    """
    sup = instance.supervisor
    if sup:
        if not sup.is_judge:
            raise ValidationError(
                {
                    "supervisor": "The supervisor field can only be set to a "
                    "judge, but '%s' does not appear to have ever "
                    "been a judge." % sup.name_full
                }
            )

    if sup and not instance.is_clerkship:
        raise ValidationError(
            "You have configured a supervisor for this field ('%s'), but it "
            "the position_type is not a clerkship. Instead it's: '%s'"
            % (sup.name_full, instance.position_type)
        )


def validate_all_or_none(instance, fields):
    """Ensure that all fields are complete or that none are complete"""
    num_fields = len(fields)
    completed_fields = sum(
        1 for f in fields if getattr(instance, f) or getattr(instance, f) == 0
    )
    all_complete = completed_fields == num_fields
    none_complete = completed_fields == 0
    if not any([all_complete, none_complete]):
        raise ValidationError(
            "%s of the following fields are complete, but either all of them need to be, or none of them need to be: %s"
            % (completed_fields, ", ".join(fields))
        )


def validate_exactly_n(instance, n, fields):
    """Ensure that exactly n of the fields has a value."""
    completed_fields = sum(1 for f in fields if getattr(instance, f))
    if completed_fields != n:
        raise ValidationError(
            "Exactly %s of the following fields can be completed (currently "
            "%s are): %s" % (n, completed_fields, ", ".join(fields))
        )


def validate_at_most_n(instance, n, fields):
    """Ensure that at most n fields are complete."""
    completed_fields = sum(1 for f in fields if getattr(instance, f))
    if completed_fields > n:
        raise ValidationError(
            "Exactly %s of the following fields can be completed (currently "
            "%s are): %s" % (n, completed_fields, ", ".join(fields))
        )


def validate_not_all(instance, fields):
    """Make sure that all of the passed fields are not complete."""
    num_fields = len(fields)
    num_completed_fields = sum(1 for f in fields if getattr(instance, f))
    if num_completed_fields == num_fields:
        # They're all completed. Boo!
        raise ValidationError(
            f"All of the following fields cannot be completed: {', '.join(fields)}"
        )


def make_choices_group_lookup(c):
    """Invert a choices variable in a model to get the group name for a
    tuple.
    """
    d = {}
    for choice, value in c:
        if isinstance(value, (list, tuple)):
            for t in value:
                d[t[0]] = choice
        else:
            d[choice] = value
    return d


def invert_choices_group_lookup(c):
    """Invert a choices variable in a model to get the key from the value.
    (key:, 'value') -> {'value': key}
    """
    d = {}
    for choice, value in c:
        d[value] = choice
    return d


def flatten_choices(self):
    """Flattened version of choices tuple on a model or form field

    Important helper when you have named groups in your choices that you need
    to have flattened.
    """
    flat = []
    for choice, value in self.choices:
        if isinstance(value, (list, tuple)):
            flat.extend(value)
        else:
            flat.append((choice, value))
    return flat


def choices_to_csv(obj, field_name):
    """Produce a CSV of possible choices for a field on an object.

    :param obj: The object type you want to inspect
    :param field_name: The field on the object you want to get the choices for
    :return s: A comma-separated list of possible values for the field
    """
    field = obj._meta.get_field(field_name)
    flat_choices = flatten_choices(field)
    # Get the second value in the choices tuple
    choice_values = [t for s, t in flat_choices]
    return oxford_join(choice_values, conjunction="or", separator=";")


def disable_auto_now_fields(*models):
    """Turns off the auto_now and auto_now_add attributes on a Model's fields,
    so that an instance of the Model can be saved with a custom value.

    Based on: https://stackoverflow.com/questions/7499767/temporarily-disable-auto-now-auto-now-add
    """
    for model in models:
        # noinspection PyProtectedMember
        for field in model._meta.local_fields:
            if hasattr(field, "auto_now"):
                field.auto_now = False
            if hasattr(field, "auto_now_add"):
                field.auto_now_add = False


@contextlib.contextmanager
def suppress_autotime(model, fields):
    """Disable auto_now and auto_now_add fields

    :param model: The model you wish to modify or an instance of it. All objects
    of this type will be modified until the end of the managed context.
    :param fields: The fields you wish to disable for the model.
    """
    _original_values = {}
    for field in model._meta.local_fields:
        if field.name in fields:
            _original_values[field.name] = {
                "auto_now": field.auto_now,
                "auto_now_add": field.auto_now_add,
            }
            field.auto_now = False
            field.auto_now_add = False
    try:
        yield
    finally:
        for field in model._meta.local_fields:
            if field.name in fields:
                field.auto_now = _original_values[field.name]["auto_now"]
                field.auto_now_add = _original_values[field.name][
                    "auto_now_add"
                ]


def linkify_orig_docket_number(agency: str, og_docket_number: str) -> str:
    """Make an originating docket number for an appellate case into a link (MVP version)

    **NOTE: These links are presented to users and should be subject to strict security checks.**

    For example, each regex should be carefully written so it accepts only the narrowest of
    matches. The risk is that:

      - Mallory uploads a bad document via the RECAP APIs (these are open APIs).
      - The code here parses that upload in a way to create a redirect on the federalregister.gov
        website.
      - federalregister.gov has an open redirect vulnerability (these are common).
      - The user clicks a link on our site that goes to federalregister.gov, which redirects the
        user to evilsite.com (b/c evilsite.com got through our checks here).
      - The user is tricked on that site into doing something bad.

    This is all quite unlikely, but we can ensure it doesn't happen by being strict about
    the inputs our regular expressions capture.

    :param agency: The administrative agency the case originated from
    :param og_docket_number: The docket number where the case was originally heard.
    :returns: A linkified version of the docket number for the user to click on, or the original if no link can be made.
    """
    # Simple pattern for Federal Register citations
    fr_match = re.search(
        r"(\d{1,3})\s*(?:FR|Fed\.?\s*Reg\.?)\s*(\d{1,5}(?:,\d{3})*)",
        og_docket_number,
    )

    if fr_match:
        volume, page = fr_match.groups()
        return f"https://www.federalregister.gov/citation/{volume}-FR-{page}"

    # NLRB pattern
    if agency == "National Labor Relations Board":
        match = re.match(
            r"^(?:NLRB-)?(\d{1,2})-?([A-Z]{2})-?(\d{1,6})$", og_docket_number
        )
        if match:
            region, case_type, number = match.groups()
            formatted_number = (
                f"{region.zfill(2)}-{case_type}-{number.zfill(6)}"
            )
            return f"https://www.nlrb.gov/case/{formatted_number}"

    # US Tax Court pattern
    if any(x in agency for x in ("Tax", "Internal Revenue")):
        match = re.match(
            r"^(?:USTC-)?(\d{1,5})-(\d{2})([A-Z])?$", og_docket_number
        )
        if match:
            number, year, letter_suffix = match.groups()
            formatted_number = f"{number.zfill(5)}-{year}"
            if letter_suffix:
                formatted_number += letter_suffix
            return (
                f"https://dawson.ustaxcourt.gov/case-detail/{formatted_number}"
            )

    # EPA non-Federal Register pattern
    if "Environmental Protection" in agency:
        match = re.match(
            r"^EPA-(HQ|R\d{2})-[A-Z]{2,5}-\d{4}-\d{4}$", og_docket_number
        )
        if match:
            return f"https://www.regulations.gov/docket/{match.group(0)}"

    """Add other agencies as feasible. Note that the Federal Register link should cover multiple agencies.
    """
    # If no match is found, return empty str
    return ""


class CSVExportMixin:

    def get_csv_columns(self, get_column_name: bool = False) -> list[str]:
        """Get list of column names required in a csv file.
        If get column name is True. It will add class name to attribute

        :param: get_column_name: bool. Whether add class name to attr name

        :return: list of attrs of class to get into csv file"""
        raise NotImplementedError(
            "Subclass must implement get_csv_columns method"
        )

    def get_column_function(self) -> dict[str, Callable[[str], str]]:
        """Get dict of attrs: function to apply on field value if it needs
        to be pre-processed before being add to csv

        returns: dict -- > {attr1: function}"""
        raise NotImplementedError(
            "Subclass must implement get_column_fuction method"
        )

    def to_csv_row(self) -> list[str]:
        """Get fields in model based on attrs column names.
        Apply function to attr value if required.
        Return list of modified values for csv row"""
        row = []
        functions = self.get_column_function()
        columns = self.get_csv_columns(get_column_name=False)
        for field in columns:
            attr = getattr(self, field)
            if not attr:
                attr = ""
            function = functions.get(field)
            if function:
                attr = function(field)
            row.append(attr)
        return row

    def add_class_name(self, attribute_name: str) -> str:
        return f"{self.__class__.__name__.lower()}_{attribute_name}"
