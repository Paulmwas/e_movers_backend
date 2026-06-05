from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from decimal import Decimal

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
from .services import (
    generate_invoice,
    simulate_payment,
    disburse_payment,
    BillingError,
    BEDROOM_PRICES,
    _distance_charge,
)
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


class QuoteView(APIView):
    """
    Public (no auth required): download the full Smartmovers price guide as a PDF.

    GET /api/v1/billing/quote/

    Returns a branded PDF showing:
      - All bedroom move prices
      - All distance bracket charges
      - A complete price matrix (every move size × every distance band)

    No input required. No records created.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        import io
        from django.http import FileResponse
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer, HRFlowable,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        # --- Static data for the PDF ---
        BEDROOM_ROWS = [
            ("one_bedroom",   "1 Bedroom",  BEDROOM_PRICES["one_bedroom"]),
            ("two_bedroom",   "2 Bedroom",  BEDROOM_PRICES["two_bedroom"]),
            ("three_bedroom", "3 Bedroom",  BEDROOM_PRICES["three_bedroom"]),
            ("four_bedroom",  "4 Bedroom",  BEDROOM_PRICES["four_bedroom"]),
            ("five_bedroom",  "5 Bedroom",  BEDROOM_PRICES["five_bedroom"]),
            ("six_bedroom",   "6 Bedroom",  BEDROOM_PRICES["six_bedroom"]),
        ]

        DISTANCE_ROWS = [
            ("Below 10 km",  Decimal("3000")),
            ("10 – 20 km",   Decimal("6000")),
            ("20 – 30 km",   Decimal("9000")),
            ("30 – 40 km",   Decimal("12000")),
            ("Above 40 km",  Decimal("12000")),
        ]

        # --- Styles ---
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        brand = colors.HexColor("#1a56db")
        light_blue = colors.HexColor("#e8f0fe")
        grey_row = colors.HexColor("#f9fafb")
        border = colors.HexColor("#d1d5db")

        title_style = ParagraphStyle(
            "title", parent=styles["Title"],
            fontSize=24, textColor=brand, spaceAfter=2, alignment=TA_CENTER,
        )
        sub_style = ParagraphStyle(
            "sub", parent=styles["Normal"],
            fontSize=10, textColor=colors.grey, spaceAfter=4, alignment=TA_CENTER,
        )
        section_style = ParagraphStyle(
            "section", parent=styles["Heading2"],
            fontSize=12, textColor=brand, spaceBefore=12, spaceAfter=4,
        )
        note_style = ParagraphStyle(
            "note", parent=styles["Normal"],
            fontSize=8, textColor=colors.grey, leading=12,
        )

        def _table_style(header_cols=None):
            cmds = [
                ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
                ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",    (0, 0), (-1, -1), 10),
                ("TOPPADDING",  (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID",        (0, 0), (-1, -1), 0.4, border),
                ("BACKGROUND",  (0, 0), (-1, 0),  brand),
                ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, grey_row]),
                ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
            ]
            if header_cols:
                for col in header_cols:
                    cmds.append(("BACKGROUND", (col, 0), (col, 0), brand))
            return TableStyle(cmds)

        elements = [
            Paragraph("Smartmovers", title_style),
            Paragraph("Professional Moving Services — Price Guide", sub_style),
            Spacer(1, 0.2 * cm),
            HRFlowable(width="100%", thickness=1.5, color=brand),
            Spacer(1, 0.3 * cm),
            Paragraph(
                "Our pricing is simple and transparent. Your total cost is made up of two parts: "
                "a <b>move size charge</b> based on the number of bedrooms, and a "
                "<b>distance charge</b> based on how far we travel. "
                "Add both together to get your final price — no hidden fees.",
                styles["Normal"],
            ),
            Spacer(1, 0.5 * cm),
        ]

        # --- Section 1: Move Size Prices ---
        elements.append(Paragraph("1.  Move Size Charges", section_style))
        bedroom_data = [["Move Size", "Base Charge (KES)"]]
        for _, label, price in BEDROOM_ROWS:
            bedroom_data.append([label, f"{price:,.0f}"])

        bedroom_table = Table(bedroom_data, colWidths=[9 * cm, 7 * cm])
        bedroom_table.setStyle(_table_style())
        elements.append(bedroom_table)
        elements.append(Spacer(1, 0.5 * cm))

        # --- Section 2: Distance Charges ---
        elements.append(Paragraph("2.  Distance Charges", section_style))
        dist_data = [["Distance", "Distance Charge (KES)"]]
        for label, price in DISTANCE_ROWS:
            dist_data.append([label, f"{price:,.0f}"])

        dist_table = Table(dist_data, colWidths=[9 * cm, 7 * cm])
        dist_table.setStyle(_table_style())
        elements.append(dist_table)
        elements.append(Spacer(1, 0.5 * cm))

        # --- Section 3: Complete Price Matrix ---
        elements.append(Paragraph("3.  Complete Price Matrix  (Move Charge + Distance Charge)", section_style))
        elements.append(Paragraph(
            "Find your move size in the left column, then your distance band across the top "
            "to get the all-in total.",
            styles["Normal"],
        ))
        elements.append(Spacer(1, 0.3 * cm))

        dist_labels = [d[0] for d in DISTANCE_ROWS]
        matrix_data = [["Move Size"] + dist_labels]

        for _, label, base in BEDROOM_ROWS:
            row = [label]
            for _, d_price in DISTANCE_ROWS:
                row.append(f"{(base + d_price):,.0f}")
            matrix_data.append(row)

        col_w = [4.2 * cm] + [2.56 * cm] * len(DISTANCE_ROWS)
        matrix_table = Table(matrix_data, colWidths=col_w)

        matrix_style_cmds = [
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
            ("FONTNAME",      (1, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID",          (0, 0), (-1, -1), 0.4, border),
            ("BACKGROUND",    (0, 0), (-1, 0),  brand),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("BACKGROUND",    (0, 1), (0, -1),  light_blue),
            ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.white, grey_row]),
        ]
        matrix_table.setStyle(TableStyle(matrix_style_cmds))
        elements.append(matrix_table)
        elements.append(Spacer(1, 0.6 * cm))

        # --- Footer note ---
        elements.append(HRFlowable(width="100%", thickness=0.5, color=border))
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph(
            "All prices are in Kenya Shillings (KES). Prices apply to residential bedroom moves. "
            "Studio and office relocations are priced on request — contact us for a custom quote. "
            "Prices are subject to change without notice. "
            "Final invoice is generated after job assignment and reflects the confirmed move details.",
            note_style,
        ))

        doc.build(elements)
        buffer.seek(0)
        return FileResponse(
            buffer, as_attachment=True,
            filename="smartmovers_pricing.pdf",
            content_type="application/pdf",
        )
