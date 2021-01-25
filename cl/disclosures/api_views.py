from rest_framework import viewsets

from cl.api.utils import LoggingMixin, DisclosureAPIUsers
from cl.disclosures.api_serializers import (
    AgreementSerializer,
    DebtSerializer,
    FinancialDisclosureSerializer,
    GiftSerializer,
    InvestmentSerializer,
    NonInvestmentIncomeSerializer,
    PositionSerializer,
    ReimbursementSerializer,
    SpouseIncomeSerializer,
)
from cl.disclosures.filters import (
    AgreementFilter,
    DebtFilter,
    FinancialDisclosureFilter,
    GiftFilter,
    InvestmentFilter,
    NonInvestmentIncomeFilter,
    PositionFilter,
    ReimbursementFilter,
    SpouseIncomeFilter,
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


class AgreementViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Agreement.objects.all().order_by("-id")
    serializer_class = AgreementSerializer
    ordering_fields = ("id", "date_created", "date_modified")
    filterset_class = AgreementFilter


class DebtViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Debt.objects.all().order_by("-id")
    serializer_class = DebtSerializer
    ordering_fields = ("id", "date_created", "date_modified")
    filterset_class = DebtFilter


class FinancialDisclosureViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = (
        FinancialDisclosure.objects.all()
        .prefetch_related(
            "agreements",
            "debts",
            "gifts",
            "investments",
            "non_investment_incomes",
            "positions",
            "reimbursements",
            "spouse_incomes",
        )
        .order_by("-id")
    )
    serializer_class = FinancialDisclosureSerializer
    filterset_class = FinancialDisclosureFilter
    ordering_fields = ("id", "date_created", "date_modified")


class GiftViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Gift.objects.all().order_by("-id")
    serializer_class = GiftSerializer
    filterset_class = GiftFilter
    ordering_fields = ("id", "date_created", "date_modified")


class InvestmentViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Investment.objects.all().order_by("-id")
    serializer_class = InvestmentSerializer
    filterset_class = InvestmentFilter
    ordering_fields = ("id", "date_created", "date_modified")


class NonInvestmentIncomeViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = NonInvestmentIncome.objects.all().order_by("-id")
    serializer_class = NonInvestmentIncomeSerializer
    filterset_class = NonInvestmentIncomeFilter
    ordering_fields = ("id", "date_created", "date_modified")


class PositionViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Position.objects.all().order_by("-id")
    serializer_class = PositionSerializer
    filterset_class = PositionFilter
    ordering_fields = ("id", "date_created", "date_modified")


class ReimbursementViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = Reimbursement.objects.all().order_by("-id")
    serializer_class = ReimbursementSerializer
    filterset_class = ReimbursementFilter
    ordering_fields = ("id", "date_created", "date_modified")


class SpouseIncomeViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (DisclosureAPIUsers,)
    queryset = SpouseIncome.objects.all().order_by("-id")
    serializer_class = SpouseIncomeSerializer
    filterset_class = SpouseIncomeFilter
    ordering_fields = ("id", "date_created", "date_modified")
