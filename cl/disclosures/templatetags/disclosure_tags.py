from django import template

from cl.disclosures.models import CODES

register = template.Library()

# Build lookup dictionaries from the CODES tuples
INCOME_GAIN_LOOKUP = dict(CODES.INCOME_GAIN)
GROSS_VALUE_LOOKUP = dict(CODES.GROSS_VALUE)
VALUATION_METHODS_LOOKUP = dict(CODES.VALUATION_METHODS)


@register.filter
def income_gain_display(value):
    """Convert income gain code to display string.

    Usage: {{ investment.income_during_reporting_period_code|income_gain_display }}
    Output: "$1,001 - 2,500 (B)" or empty string if not found
    """
    if value is None or value == "" or value == -1 or value == "-1":
        return ""
    label = INCOME_GAIN_LOOKUP.get(str(value))
    if label:
        return f"${label} ({value})"
    return str(value)


@register.filter
def gross_value_display(value):
    """Convert gross value code to display string.

    Usage: {{ investment.gross_value_code|gross_value_display }}
    Output: "$15,001 - 50,000 (K)" or empty string if not found
    """
    if value is None or value == "" or value == -1 or value == "-1":
        return ""
    label = GROSS_VALUE_LOOKUP.get(str(value))
    if label:
        return f"${label} ({value})"
    return str(value)


@register.filter
def valuation_method_display(value):
    """Convert valuation method code to display string.

    Usage: {{ investment.gross_value_method|valuation_method_display }}
    Output: "Appraisal (Q)" or empty string if not found
    """
    if value is None or value == "" or value == -1 or value == "-1":
        return ""
    label = VALUATION_METHODS_LOOKUP.get(str(value))
    if label:
        return f"{label} ({value})"
    return str(value)


@register.filter
def is_failed_extraction(value):
    """Check if value indicates failed extraction.

    Usage: {% if investment.gross_value_code|is_failed_extraction %}...{% endif %}
    """
    return value == -1 or value == "-1"
