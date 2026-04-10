from rest_framework_filters import filters

from cl.api.utils import (
    BASIC_TEXT_LOOKUPS,
    BOOLEAN_LOOKUPS,
    DATETIME_LOOKUPS,
    INTEGER_LOOKUPS,
    NoEmptyFilterSet,
)
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
from cl.people_db.models import Person

disclosure_fields = {
    "id": INTEGER_LOOKUPS,
    "date_created": DATETIME_LOOKUPS,
    "date_modified": DATETIME_LOOKUPS,
    "redacted": BOOLEAN_LOOKUPS,
}


class AgreementFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        "cl.disclosures.filters.FinancialDisclosureFilter",
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Agreement
        fields = disclosure_fields.copy()
        fields.update(
            {
                "parties_and_terms": BASIC_TEXT_LOOKUPS,
                "date_raw": BASIC_TEXT_LOOKUPS,
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class DebtFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        "cl.disclosures.filters.FinancialDisclosureFilter",
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Debt
        fields = disclosure_fields.copy()
        fields.update(
            {
                "creditor_name": BASIC_TEXT_LOOKUPS,
                "description": BASIC_TEXT_LOOKUPS,
                "value_code": ["exact"],
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class FinancialDisclosureFilter(NoEmptyFilterSet):
    agreements = filters.RelatedFilter(
        AgreementFilter,
        queryset=Agreement.objects.all(),
    )
    debts = filters.RelatedFilter(
        DebtFilter,
        queryset=Debt.objects.all(),
    )
    gifts = filters.RelatedFilter(
        "cl.disclosures.filters.GiftFilter",
        queryset=Gift.objects.all(),
    )
    investments = filters.RelatedFilter(
        "cl.disclosures.filters.InvestmentFilter",
        queryset=Investment.objects.all(),
    )
    non_investment_incomes = filters.RelatedFilter(
        "cl.disclosures.filters.NonInvestmentIncomeFilter",
        queryset=NonInvestmentIncome.objects.all(),
    )
    person = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter",
        queryset=Person.objects.all(),
    )
    positions = filters.RelatedFilter(
        "cl.disclosures.filters.PositionFilter",
        queryset=Position.objects.all(),
    )
    reimbursements = filters.RelatedFilter(
        "cl.disclosures.filters.ReimbursementFilter",
        queryset=Reimbursement.objects.all(),
    )
    spouse_incomes = filters.RelatedFilter(
        "cl.disclosures.filters.SpouseIncomeFilter",
        queryset=SpouseIncome.objects.all(),
    )

    class Meta:
        model = FinancialDisclosure
        fields = {
            "id": INTEGER_LOOKUPS,
            "person": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "addendum_content_raw": BASIC_TEXT_LOOKUPS,
            "has_been_extracted": BOOLEAN_LOOKUPS,
        }


class GiftFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Gift
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "source": BASIC_TEXT_LOOKUPS,
            "description": BASIC_TEXT_LOOKUPS,
            "value": BASIC_TEXT_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class InvestmentFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Investment
        fields = disclosure_fields.copy()
        fields.update(
            {
                "description": BASIC_TEXT_LOOKUPS,
                "gross_value_code": ["exact"],
                "income_during_reporting_period_code": ["exact"],
                "transaction_during_reporting_period": BASIC_TEXT_LOOKUPS,
                "transaction_value_code": ["exact"],
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class NonInvestmentIncomeFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = NonInvestmentIncome
        fields = disclosure_fields.copy()
        fields.update(
            {
                "date_raw": BASIC_TEXT_LOOKUPS,
                "source_type": BASIC_TEXT_LOOKUPS,
                "income_amount": BASIC_TEXT_LOOKUPS,
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class PositionFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Position
        fields = disclosure_fields.copy()
        fields.update(
            {
                "position": BASIC_TEXT_LOOKUPS,
                "organization_name": BASIC_TEXT_LOOKUPS,
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class ReimbursementFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Reimbursement
        fields = disclosure_fields.copy()
        fields.update(
            {
                "date_raw": BASIC_TEXT_LOOKUPS,
                "location": BASIC_TEXT_LOOKUPS,
                "source": BASIC_TEXT_LOOKUPS,
                "purpose": BASIC_TEXT_LOOKUPS,
                "items_paid_or_provided": BASIC_TEXT_LOOKUPS,
                "redacted": BOOLEAN_LOOKUPS,
            }
        )


class SpouseIncomeFilter(NoEmptyFilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = SpouseIncome
        fields = disclosure_fields.copy()
        fields.update(
            {
                "date_raw": BASIC_TEXT_LOOKUPS,
                "source_type": BASIC_TEXT_LOOKUPS,
                "redacted": BOOLEAN_LOOKUPS,
            }
        )
