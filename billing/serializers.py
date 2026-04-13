from rest_framework import serializers
from decimal import Decimal
from .models import Invoice, Payment, PaymentDisbursement


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "amount",
            "method",
            "method_display",
            "status",
            "status_display",
            "transaction_id",
            "payment_date",
            "notes",
            "recorded_by",
            "recorded_by_name",
        ]
        read_only_fields = [
            "id",
            "status",
            "transaction_id",
            "payment_date",
            "recorded_by",
        ]

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.get_full_name() if obj.recorded_by else None


class InvoiceSerializer(serializers.ModelSerializer):
    payments = PaymentSerializer(many=True, read_only=True)
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )
    job_title = serializers.CharField(source="job.title", read_only=True)
    customer_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "job",
            "job_title",
            "customer_name",
            "base_charge",
            "distance_charge",
            "staff_charge",
            "truck_charge",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "total_amount",
            "amount_paid",
            "balance_due",
            "payment_status",
            "payment_status_display",
            "due_date",
            "notes",
            "payments",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "base_charge",
            "distance_charge",
            "staff_charge",
            "truck_charge",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "total_amount",
            "amount_paid",
            "balance_due",
            "payment_status",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj):
        return obj.job.customer.get_full_name()

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )
    job_title = serializers.CharField(source="job.title", read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "job",
            "job_title",
            "customer_name",
            "total_amount",
            "amount_paid",
            "balance_due",
            "payment_status",
            "payment_status_display",
            "due_date",
            "created_at",
        ]

    def get_customer_name(self, obj):
        return obj.job.customer.get_full_name()


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    """Fields admin can edit on an existing invoice."""
    class Meta:
        model = Invoice
        fields = ["due_date", "notes"]


class GenerateInvoiceSerializer(serializers.Serializer):
    """Request body for POST /billing/invoices/generate/"""
    job_id = serializers.IntegerField()
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class SimulatePaymentSerializer(serializers.Serializer):
    """Request body for POST /billing/invoices/<pk>/pay/"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentDisbursementSerializer(serializers.ModelSerializer):
    """Full representation of a payment disbursement record."""
    staff_name = serializers.SerializerMethodField()
    staff_email = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    disbursed_by_name = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="invoice.job.title", read_only=True)

    class Meta:
        model = PaymentDisbursement
        fields = [
            "id",
            "invoice",
            "job_title",
            "staff",
            "staff_name",
            "staff_email",
            "amount",
            "status",
            "status_display",
            "disbursed_by",
            "disbursed_by_name",
            "disbursed_at",
            "transaction_ref",
            "notes",
        ]
        read_only_fields = [
            "id", "status", "disbursed_by", "disbursed_at", "transaction_ref",
        ]

    def get_staff_name(self, obj):
        return obj.staff.get_full_name()

    def get_staff_email(self, obj):
        return obj.staff.email

    def get_disbursed_by_name(self, obj):
        return obj.disbursed_by.get_full_name() if obj.disbursed_by else None
