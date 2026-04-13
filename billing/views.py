from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import Invoice, Payment, PaymentDisbursement
from .filters import InvoiceFilter, PaymentFilter
from .serializers import (
    InvoiceSerializer,
    InvoiceListSerializer,
    InvoiceUpdateSerializer,
    GenerateInvoiceSerializer,
    SimulatePaymentSerializer,
    PaymentSerializer,
    PaymentDisbursementSerializer,
)
from .services import generate_invoice, simulate_payment, disburse_payment, BillingError
from jobs.models import Job
from accounts.permissions import IsMoverAdmin, IsAdminOrStaff


class InvoiceListView(generics.ListAPIView):
    """
    Admin & Staff: list invoices.

    Query params:
      ?payment_status=unpaid|partial|paid|waived
      ?job=<job_id>
    """
    serializer_class = InvoiceListSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = InvoiceFilter
    ordering_fields = ["created_at", "total_amount", "due_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Invoice.objects.select_related("job__customer", "created_by")
            .prefetch_related("payments")
            .all()
        )


class GenerateInvoiceView(APIView):
    """
    Admin only: calculate costs and create (or refresh) an invoice for a job.

    POST body:
      {
        "job_id": 1,
        "due_date": "2025-12-31",  // optional
        "notes": ""                // optional
      }

    Can be called multiple times on the same job as long as the
    invoice isn't fully PAID yet — useful for updating after
    staff/truck assignments change pre-completion.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request):
        serializer = GenerateInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = get_object_or_404(
            Job.objects.prefetch_related("assignments", "job_trucks"),
            pk=serializer.validated_data["job_id"],
        )

        try:
            invoice = generate_invoice(
                job=job,
                created_by=request.user,
                due_date=serializer.validated_data.get("due_date"),
                notes=serializer.validated_data.get("notes", ""),
            )
        except BillingError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )


class InvoiceDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   — Admin & Staff: full invoice detail with payment history
    PATCH — Admin only: update due_date or notes
    """
    queryset = (
        Invoice.objects.select_related("job__customer", "created_by")
        .prefetch_related("payments__recorded_by")
    )

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return InvoiceUpdateSerializer
        return InvoiceSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), IsAdminOrStaff()]
        return [IsAuthenticated(), IsMoverAdmin()]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = InvoiceUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(InvoiceSerializer(instance).data)


class SimulatePaymentView(APIView):
    """
    Admin only: record a simulated payment against an invoice.

    POST body:
      {
        "amount": 5000.00,
        "method": "mpesa",   // cash | mpesa | bank_transfer | card
        "notes": ""          // optional
      }

    Generates a fake transaction_id (SIM-MPE-...) and immediately
    marks the payment as COMPLETED. The invoice balance_due is
    recalculated after every payment.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.prefetch_related("payments"),
            pk=pk,
        )
        serializer = SimulatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment = simulate_payment(
                invoice=invoice,
                amount=serializer.validated_data["amount"],
                method=serializer.validated_data["method"],
                recorded_by=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except BillingError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Refresh invoice from DB to return updated balances
        invoice.refresh_from_db()

        return Response(
            {
                "message": "Payment recorded successfully.",
                "payment": PaymentSerializer(payment).data,
                "invoice": InvoiceSerializer(invoice).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentListView(generics.ListAPIView):
    """
    Admin & Staff: full payment history with filters.

    Query params:
      ?method=cash|mpesa|bank_transfer|card
      ?status=pending|completed|failed|refunded
      ?invoice=<invoice_id>
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = PaymentFilter
    ordering_fields = ["payment_date", "amount"]
    ordering = ["-payment_date"]

    def get_queryset(self):
        return Payment.objects.select_related(
            "invoice__job__customer", "recorded_by"
        ).all()


class DisbursePaymentView(APIView):
    """
    Admin only: disburse the collected invoice amount equally to all
    assigned staff members. Creates one PaymentDisbursement per staff member.

    POST /api/v1/billing/invoices/<pk>/disburse/

    No request body required.

    Business rules:
      - Invoice must be fully PAID.
      - Disbursement can only happen once per invoice (idempotent guard).
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.prefetch_related(
                "disbursements", "job__assignments__staff"
            ),
            pk=pk,
        )

        try:
            disbursements = disburse_payment(
                invoice=invoice,
                disbursed_by=request.user,
            )
        except BillingError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"Payment disbursed to {disbursements.count()} staff member(s).",
                "disbursements": PaymentDisbursementSerializer(
                    disbursements, many=True
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class DisbursementListView(generics.ListAPIView):
    """
    Admin only: list all disbursement records with optional filters.

    Query params:
      ?invoice=<invoice_id>
      ?staff=<user_id>
      ?status=pending|disbursed
    """
    serializer_class = PaymentDisbursementSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["invoice", "staff", "status"]
    ordering_fields = ["disbursed_at", "amount"]
    ordering = ["-disbursed_at"]

    def get_queryset(self):
        return PaymentDisbursement.objects.select_related(
            "invoice__job", "staff", "disbursed_by"
        ).all()
