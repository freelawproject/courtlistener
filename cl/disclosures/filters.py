from rest_framework_filters import FilterSet, filters

from cl.api.utils import DATETIME_LOOKUPS, BOOLEAN_LOOKUPS, ALL_TEXT_LOOKUPS
from cl.disclosures.models import (
    Agreement,
    Debt,
    FinancialDisclosure,
    Gift,
    Investment,
    NonInvestmentIncome,
    Position,
    Reimbursement,
    SpouseIncome,
)


class AgreementFilter(FilterSet):
    class Meta:
        model = Agreement
        fields = {
            "id": ["exact"],
            "parties_and_terms": ALL_TEXT_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class DebtFilter(FilterSet):
    class Meta:
        model = Debt
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class FinancialDisclosureFilter(FilterSet):
    class Meta:
        model = FinancialDisclosure
        fields = {
            "id": ["exact"],
            "person": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "addendum_content_raw": ALL_TEXT_LOOKUPS,
            "has_been_extracted": BOOLEAN_LOOKUPS,
        }


class GiftFilter(FilterSet):
    class Meta:
        model = Gift
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class InvestmentFilter(FilterSet):
    class Meta:
        model = Investment
        fields = {
            "id": ["exact"],
            "gross_value_code": ["exact"],
            "income_during_reporting_period_code": ["exact"],
            "redacted": BOOLEAN_LOOKUPS,
            "description": ALL_TEXT_LOOKUPS,
            "transaction_during_reporting_period": ALL_TEXT_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
        }


class NonInvestmentIncomeFilter(FilterSet):
    class Meta:
        model = NonInvestmentIncome
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class PositionFilter(FilterSet):
    class Meta:
        model = Position
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class ReimbursementFilter(FilterSet):
    class Meta:
        model = Reimbursement
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class SpouseIncomeFilter(FilterSet):
    class Meta:
        model = SpouseIncome
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }
