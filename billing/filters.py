import django_filters
from .models import Invoice, Payment


class InvoiceFilter(django_filters.FilterSet):
    """
    ?payment_status=unpaid|partial|paid|waived
    ?job=<id>
    ?due_before=YYYY-MM-DD
    ?due_after=YYYY-MM-DD
    ?total_min=1000
    ?total_max=50000
    """
    due_before = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    due_after = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    total_min = django_filters.NumberFilter(field_name="total_amount", lookup_expr="gte")
    total_max = django_filters.NumberFilter(field_name="total_amount", lookup_expr="lte")

    class Meta:
        model = Invoice
        fields = ["payment_status", "job"]


class PaymentFilter(django_filters.FilterSet):
    """
    ?method=mpesa|cash|bank_transfer|card
    ?status=completed|pending|failed|refunded
    ?invoice=<id>
    ?paid_after=YYYY-MM-DD
    ?paid_before=YYYY-MM-DD
    """
    paid_after = django_filters.DateFilter(field_name="payment_date", lookup_expr="date__gte")
    paid_before = django_filters.DateFilter(field_name="payment_date", lookup_expr="date__lte")

    class Meta:
        model = Payment
        fields = ["method", "status", "invoice"]
