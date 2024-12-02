from rest_framework import viewsets
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

from cl.api.api_permissions import V3APIPermission
from cl.api.utils import LoggingMixin
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
    queryset = Agreement.objects.all().order_by("-id")
    serializer_class = AgreementSerializer
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    filterset_class = AgreementFilter
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class DebtViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Debt.objects.all().order_by("-id")
    serializer_class = DebtSerializer
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    filterset_class = DebtFilter
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class FinancialDisclosureViewSet(LoggingMixin, viewsets.ModelViewSet):
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
            "person",
        )
        .order_by("-id")
    )
    serializer_class = FinancialDisclosureSerializer
    filterset_class = FinancialDisclosureFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class GiftViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Gift.objects.all().order_by("-id")
    serializer_class = GiftSerializer
    filterset_class = GiftFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class InvestmentViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Investment.objects.all().order_by("-id")
    serializer_class = InvestmentSerializer
    filterset_class = InvestmentFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class NonInvestmentIncomeViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = NonInvestmentIncome.objects.all().order_by("-id")
    serializer_class = NonInvestmentIncomeSerializer
    filterset_class = NonInvestmentIncomeFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class PositionViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Position.objects.all().order_by("-id")
    serializer_class = PositionSerializer
    filterset_class = PositionFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class ReimbursementViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Reimbursement.objects.all().order_by("-id")
    serializer_class = ReimbursementSerializer
    filterset_class = ReimbursementFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]


class SpouseIncomeViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = SpouseIncome.objects.all().order_by("-id")
    serializer_class = SpouseIncomeSerializer
    filterset_class = SpouseIncomeFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
