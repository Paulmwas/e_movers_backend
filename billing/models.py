from django.db import models
from django.conf import settings
from jobs.models import Job


class Invoice(models.Model):
    """
    One invoice per job. Generated after a job is created (or on-demand).
    Costs are calculated by billing/services.py and stored as line items
    so the frontend can render a transparent breakdown.

    Payment is simulated — no real gateway integration.
    """

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        WAIVED = "waived", "Waived"

    job = models.OneToOneField(Job, on_delete=models.PROTECT, related_name="invoice")

    # Cost breakdown (in KES)
    base_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    distance_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    staff_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    truck_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.1600)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )

    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self):
        return f"Invoice #{self.pk} — {self.job.title} ({self.payment_status})"

    def refresh_balance(self):
        """
        Recompute balance_due and payment_status after a payment is recorded.
        Called by the payment service after saving a Payment.
        """
        total_paid = sum(
            p.amount for p in self.payments.filter(status=Payment.Status.COMPLETED)
        )
        self.amount_paid = total_paid
        self.balance_due = max(self.total_amount - total_paid, 0)

        if total_paid <= 0:
            self.payment_status = self.PaymentStatus.UNPAID
        elif self.balance_due == 0:
            self.payment_status = self.PaymentStatus.PAID
        else:
            self.payment_status = self.PaymentStatus.PARTIAL

        self.save(update_fields=[
            "amount_paid", "balance_due", "payment_status", "updated_at"
        ])


class Payment(models.Model):
    """
    Simulated payment record against an invoice.
    A real gateway integration would replace `_simulate_payment` in billing/services.py
    while keeping this model intact.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MPESA = "mpesa", "M-Pesa"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CARD = "card", "Card"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.COMPLETED
    )

    # Simulated gateway reference — real gateway would populate this
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )

    class Meta:
        ordering = ["-payment_date"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"Payment {self.transaction_id} — KES {self.amount} ({self.method})"


class PaymentDisbursement(models.Model):
    """
    Simulated per-staff payment disbursement for a completed job.

    After the admin has collected payment on the invoice, they trigger
    disburse_payment() which splits the collected amount equally among
    all assigned staff and creates one PaymentDisbursement record per
    staff member.

    Business rules (enforced at service layer):
      - Invoice must be PAID before disbursement.
      - Disbursement is idempotent — calling disburse_payment twice
        on the same invoice raises BillingError.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DISBURSED = "disbursed", "Disbursed"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="disbursements"
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="disbursements",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DISBURSED
    )
    disbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="made_disbursements",
    )
    disbursed_at = models.DateTimeField(auto_now_add=True)
    transaction_ref = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("invoice", "staff")]
        ordering = ["-disbursed_at"]
        verbose_name = "Payment Disbursement"
        verbose_name_plural = "Payment Disbursements"

    def __str__(self):
        return (
            f"Disbursement {self.transaction_ref} — "
            f"KES {self.amount} to {self.staff.get_full_name()}"
        )
