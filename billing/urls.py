from django.urls import path
from . import views

urlpatterns = [
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/generate/", views.GenerateInvoiceView.as_view(), name="invoice_generate"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/pay/", views.SimulatePaymentView.as_view(), name="invoice_pay"),
    path("invoices/<int:pk>/disburse/", views.DisbursePaymentView.as_view(), name="invoice_disburse"),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("disbursements/", views.DisbursementListView.as_view(), name="disbursement_list"),
]
