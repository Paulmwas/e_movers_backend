"""
billing/services.py
===================
All billing business logic in one place.

Pricing model (all amounts in KES):
  Bedroom jobs (1–6 bedrooms):
    bedroom_charge = lookup from BEDROOM_PRICES table
    distance_charge = lookup from DISTANCE_BRACKETS table
    total_amount = bedroom_charge + distance_charge  (no tax for bedroom moves)

  Non-bedroom jobs (studio, office_small, office_large) — legacy formula:
    base_charge      = 2,000
    distance_charge  = 100 × estimated_distance_km
    staff_charge     = 500 × assigned_staff_count
    truck_charge     = 1,500 × assigned_truck_count
    subtotal         = sum of above
    tax_amount       = subtotal × 16%
    total_amount     = subtotal + tax_amount

Disbursement model:
  Each assigned staff member receives a flat KES 500.
  Remainder (amount_paid − 500 × staff_count) is recorded as company_profit
  on the Invoice and surfaced in billing reports.

Simulated payment:
  Generates a fake transaction_id (SIM-<timestamp>-<random>),
  immediately marks payment as COMPLETED, then refreshes invoice balance.
"""

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Invoice, Payment, PaymentDisbursement
from jobs.models import Job


# ---------------------------------------------------------------------------
# Bedroom-based pricing tables (KES)
# ---------------------------------------------------------------------------

BEDROOM_PRICES = {
    "one_bedroom":   Decimal("10000.00"),
    "two_bedroom":   Decimal("14000.00"),
    "three_bedroom": Decimal("20000.00"),
    "four_bedroom":  Decimal("24000.00"),
    "five_bedroom":  Decimal("28000.00"),
    "six_bedroom":   Decimal("32000.00"),
}

# Distance brackets: (max_km_exclusive, price)  — last entry is the cap
DISTANCE_BRACKETS = [
    (10,  Decimal("3000.00")),
    (20,  Decimal("6000.00")),
    (30,  Decimal("9000.00")),
    (40,  Decimal("12000.00")),
    (None, Decimal("12000.00")),  # >40 km — cap at 12,000
]

# Legacy pricing constants used for non-bedroom move sizes
LEGACY_BASE_CHARGE = Decimal("2000.00")
LEGACY_RATE_PER_KM = Decimal("100.00")
LEGACY_RATE_PER_STAFF = Decimal("500.00")
LEGACY_RATE_PER_TRUCK = Decimal("1500.00")
LEGACY_TAX_RATE = Decimal("0.1600")

STAFF_DISBURSEMENT_FLAT = Decimal("500.00")


def _distance_charge(distance_km: Decimal) -> Decimal:
    km = float(distance_km)
    for max_km, price in DISTANCE_BRACKETS:
        if max_km is None or km < max_km:
            return price
    return DISTANCE_BRACKETS[-1][1]


class BillingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------

@transaction.atomic
def generate_invoice(job: Job, created_by, due_date=None, notes: str = "") -> Invoice:
    """
    Calculate costs for a job and create (or update) its invoice.

    For 1–6 bedroom jobs: bedroom price + distance bracket (no tax).
    For studio/office moves: legacy formula with tax.

    Can be called:
      - After job creation (generates a quote)
      - After job completion (confirms final amounts)

    Raises BillingError if the job already has a PAID invoice.
    """
    if hasattr(job, "invoice"):
        existing: Invoice = job.invoice
        if existing.payment_status == Invoice.PaymentStatus.PAID:
            raise BillingError(
                "This job already has a fully paid invoice. "
                "It cannot be regenerated."
            )

    distance_km = Decimal(str(job.estimated_distance_km))

    if job.move_size in BEDROOM_PRICES:
        # Bedroom move — new pricing model
        # Staff/truck charges are informational (show cost allocation); they do
        # not inflate the customer total — total = bedroom + distance only.
        staff_count = job.assignments.count()
        truck_count = job.job_trucks.count()
        base_charge = BEDROOM_PRICES[job.move_size]
        dist_charge = _distance_charge(distance_km)
        staff_charge = STAFF_DISBURSEMENT_FLAT * staff_count
        truck_charge = LEGACY_RATE_PER_TRUCK * truck_count
        subtotal = base_charge + dist_charge
        tax_rate = Decimal("0.00")
        tax_amount = Decimal("0.00")
        total_amount = subtotal
    else:
        # Studio / office — legacy formula
        staff_count = job.assignments.count()
        truck_count = job.job_trucks.count()
        base_charge = LEGACY_BASE_CHARGE
        dist_charge = LEGACY_RATE_PER_KM * distance_km
        staff_charge = LEGACY_RATE_PER_STAFF * staff_count
        truck_charge = LEGACY_RATE_PER_TRUCK * truck_count
        subtotal = base_charge + dist_charge + staff_charge + truck_charge
        tax_rate = LEGACY_TAX_RATE
        tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
        total_amount = subtotal + tax_amount

    invoice_data = {
        "base_charge": base_charge,
        "distance_charge": dist_charge,
        "staff_charge": staff_charge,
        "truck_charge": truck_charge,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "balance_due": total_amount,
        "payment_status": Invoice.PaymentStatus.UNPAID,
        "due_date": due_date,
        "notes": notes,
        "created_by": created_by,
    }

    if hasattr(job, "invoice"):
        for field, value in invoice_data.items():
            setattr(job.invoice, field, value)
        job.invoice.balance_due = max(
            total_amount - job.invoice.amount_paid, Decimal("0.00")
        )
        if job.invoice.amount_paid >= total_amount:
            job.invoice.payment_status = Invoice.PaymentStatus.PAID
        elif job.invoice.amount_paid > 0:
            job.invoice.payment_status = Invoice.PaymentStatus.PARTIAL
        job.invoice.save()
        return job.invoice

    return Invoice.objects.create(job=job, amount_paid=Decimal("0.00"), **invoice_data)


# ---------------------------------------------------------------------------
# Simulated payment
# ---------------------------------------------------------------------------

@transaction.atomic
def simulate_payment(invoice: Invoice, amount: Decimal, method: str, recorded_by, notes: str = "") -> Payment:
    """
    Record a simulated payment against an invoice.

    Validation:
      - Invoice must not already be fully PAID.
      - Payment amount must be > 0.
      - Payment amount must not exceed outstanding balance_due.

    After saving the Payment, the Invoice.refresh_balance() is called
    to update amount_paid, balance_due, and payment_status.
    """
    if invoice.payment_status == Invoice.PaymentStatus.PAID:
        raise BillingError("This invoice is already fully paid.")

    if amount <= Decimal("0.00"):
        raise BillingError("Payment amount must be greater than zero.")

    if amount > invoice.balance_due:
        raise BillingError(
            f"Payment amount (KES {amount}) exceeds the outstanding "
            f"balance (KES {invoice.balance_due})."
        )

    transaction_id = _generate_transaction_id(method)

    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        status=Payment.Status.COMPLETED,
        transaction_id=transaction_id,
        notes=notes,
        recorded_by=recorded_by,
    )

    # Refresh balance totals on the invoice
    invoice.refresh_balance()

    return payment


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_transaction_id(method: str) -> str:
    """
    Generate a fake gateway reference that is clearly simulated.
    Format: SIM-<METHOD_PREFIX>-<TIMESTAMP>-<8 HEX CHARS>
    Example: SIM-MPE-1714055400-A3F7B291
    """
    prefix_map = {
        Payment.Method.MPESA: "MPE",
        Payment.Method.CASH: "CSH",
        Payment.Method.BANK_TRANSFER: "BNK",
        Payment.Method.CARD: "CRD",
    }
    prefix = prefix_map.get(method, "SIM")
    ts = int(timezone.now().timestamp())
    rand = uuid.uuid4().hex[:8].upper()
    return f"SIM-{prefix}-{ts}-{rand}"


# ---------------------------------------------------------------------------
# Payment Disbursement
# ---------------------------------------------------------------------------

@transaction.atomic
def disburse_payment(invoice: Invoice, disbursed_by) -> list:
    """
    Disburse a flat KES 500 to each assigned staff member.
    The remainder (amount_paid − 500 × staff_count) is recorded as
    company_profit on the invoice.

    Rules:
      - Invoice must have payment_status=PAID.
      - Disbursement is idempotent: raises BillingError if already done.

    Parameters
    ----------
    invoice : Invoice
    disbursed_by : User

    Returns
    -------
    QuerySet[PaymentDisbursement]

    Raises
    ------
    BillingError
    """
    if invoice.payment_status != Invoice.PaymentStatus.PAID:
        raise BillingError(
            f"Cannot disburse payment for an invoice with status "
            f"'{invoice.get_payment_status_display()}'. "
            f"The invoice must be fully PAID first."
        )

    if invoice.disbursements.exists():
        raise BillingError(
            "Payment has already been disbursed for this invoice."
        )

    staff_assignments = invoice.job.assignments.select_related("staff").all()
    staff_list = [a.staff for a in staff_assignments]

    if not staff_list:
        raise BillingError(
            "Cannot disburse: no staff are assigned to this job."
        )

    staff_count = len(staff_list)
    per_person = STAFF_DISBURSEMENT_FLAT
    total_staff_payout = per_person * staff_count
    company_profit = max(invoice.amount_paid - total_staff_payout, Decimal("0.00"))

    ts = int(timezone.now().timestamp())
    disbursements = []

    for staff in staff_list:
        ref = f"SIM-DSB-{ts}-{uuid.uuid4().hex[:8].upper()}"
        disbursements.append(
            PaymentDisbursement(
                invoice=invoice,
                staff=staff,
                amount=per_person,
                status=PaymentDisbursement.Status.DISBURSED,
                disbursed_by=disbursed_by,
                transaction_ref=ref,
            )
        )

    PaymentDisbursement.objects.bulk_create(disbursements)

    # Record company profit on the invoice
    invoice.company_profit = company_profit
    invoice.save(update_fields=["company_profit", "updated_at"])

    # Send notification to each staff member
    try:
        from notifications.services import notify_many
        notify_many(
            recipients=staff_list,
            notification_type="payment_disbursed",
            title=f"Payment Received — {invoice.job.title}",
            body=(
                f"Your payment of KES {per_person} for '{invoice.job.title}' "
                f"has been disbursed. Thank you for your hard work!"
            ),
            job=invoice.job,
        )
    except Exception:
        pass  # Notifications are non-critical; don't break disbursement

    return PaymentDisbursement.objects.filter(invoice=invoice).select_related("staff")
