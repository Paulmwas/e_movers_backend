from django.contrib import admin
from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ["transaction_id", "payment_date", "recorded_by"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "id", "job", "total_amount", "amount_paid",
        "balance_due", "payment_status", "due_date", "created_at",
    ]
    list_filter = ["payment_status"]
    readonly_fields = [
        "base_charge", "distance_charge", "staff_charge", "truck_charge",
        "subtotal", "tax_rate", "tax_amount", "total_amount",
        "amount_paid", "balance_due", "created_by", "created_at", "updated_at",
    ]
    search_fields = ["job__title", "job__customer__email"]
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "transaction_id", "invoice", "amount", "method",
        "status", "payment_date", "recorded_by",
    ]
    list_filter = ["method", "status"]
    readonly_fields = ["transaction_id", "payment_date", "recorded_by"]
