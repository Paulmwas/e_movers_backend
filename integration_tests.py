"""
integration_tests.py
====================
End-to-end test suite for the entire E-Movers API.
Exercises every endpoint, validates status codes, response shapes,
permission gates, and business-rule enforcement.

Run:
    DJANGO_SETTINGS_MODULE=e_movers.settings python integration_tests.py
"""

import os
import sys
import json
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_movers.settings")
django.setup()

from django.test import TestCase, Client
from django.test.utils import setup_test_environment

setup_test_environment()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class APIClient:
    def __init__(self):
        self.client = Client()
        self.access_token = None

    def _headers(self):
        if self.access_token:
            return {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}
        return {}

    def post(self, url, data=None, **kwargs):
        return self.client.post(
            url, data=json.dumps(data or {}),
            content_type="application/json",
            **self._headers(), **kwargs,
        )

    def get(self, url, **kwargs):
        return self.client.get(url, **self._headers(), **kwargs)

    def patch(self, url, data=None, **kwargs):
        return self.client.patch(
            url, data=json.dumps(data or {}),
            content_type="application/json",
            **self._headers(), **kwargs,
        )

    def delete(self, url, **kwargs):
        return self.client.delete(url, **self._headers(), **kwargs)

    def login(self, email, password):
        r = self.post("/api/v1/auth/login/", {"email": email, "password": password})
        assert r.status_code == 200, f"Login failed for {email}: {r.content}"
        data = r.json()
        self.access_token = data["tokens"]["access"]
        self.refresh_token = data["tokens"]["refresh"]
        return data


def ok(r, expected=200, label=""):
    body = r.json() if r.content else {}
    assert r.status_code == expected, (
        f"[{label}] Expected {expected}, got {r.status_code}. Body: {body}"
    )
    return body


def has_keys(body, *keys, label=""):
    for k in keys:
        assert k in body, f"[{label}] Missing key '{k}' in: {body}"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
RESULTS = []


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        RESULTS.append(("PASS", name))
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        RESULTS.append(("FAIL", name, str(e)))
        print(f"  FAIL  {name}")
        print(f"         {e}")


# ---------------------------------------------------------------------------
# Setup — ensure clean state
# ---------------------------------------------------------------------------

from django.core.management import call_command
import io

call_command("seed_data", flush=True, stdout=io.StringIO(), stderr=io.StringIO())

admin_client = APIClient()
staff_client = APIClient()

# ===========================================================================
# 1. AUTH
# ===========================================================================
print("\n--- AUTH ---")


def test_login_admin():
    data = admin_client.login("admin@emovers.co.ke", "Admin1234!")
    has_keys(data, "user", "tokens", label="login")
    assert data["user"]["role"] == "mover-admin"


def test_login_staff():
    data = staff_client.login("staff01@emovers.co.ke", "Staff1234!")
    assert data["user"]["role"] == "mover-staff"


def test_login_bad_password():
    c = APIClient()
    r = c.post("/api/v1/auth/login/", {"email": "admin@emovers.co.ke", "password": "wrong"})
    ok(r, 401, "bad_password")


def test_login_inactive_user():
    from accounts.models import User
    User.objects.filter(email="staff15@emovers.co.ke").update(is_active=False)
    c = APIClient()
    r = c.post("/api/v1/auth/login/", {"email": "staff15@emovers.co.ke", "password": "Staff1234!"})
    ok(r, 403, "inactive_user")
    User.objects.filter(email="staff15@emovers.co.ke").update(is_active=True)


def test_me_get():
    r = admin_client.get("/api/v1/auth/me/")
    body = ok(r, 200, "me_get")
    has_keys(body, "id", "email", "role", label="me")


def test_me_patch():
    r = admin_client.patch("/api/v1/auth/me/", {"first_name": "Super"})
    body = ok(r, 200, "me_patch")
    assert body["first_name"] == "Super"
    admin_client.patch("/api/v1/auth/me/", {"first_name": "System"})


def test_me_unauthenticated():
    c = APIClient()
    r = c.get("/api/v1/auth/me/")
    ok(r, 401, "me_unauth")


def test_change_password():
    r = admin_client.post("/api/v1/auth/change-password/", {
        "old_password": "Admin1234!",
        "new_password": "Admin5678!",
        "new_password_confirm": "Admin5678!",
    })
    ok(r, 200, "change_password")
    # Restore
    admin_client.post("/api/v1/auth/change-password/", {
        "old_password": "Admin5678!",
        "new_password": "Admin1234!",
        "new_password_confirm": "Admin1234!",
    })


def test_register_by_admin():
    r = admin_client.post("/api/v1/auth/register/", {
        "email": "newstaff@emovers.co.ke",
        "first_name": "New",
        "last_name": "Staff",
        "phone": "+254799000001",
        "role": "mover-staff",
        "password": "Staff1234!",
        "password_confirm": "Staff1234!",
    })
    ok(r, 201, "register")


def test_register_by_staff_forbidden():
    r = staff_client.post("/api/v1/auth/register/", {
        "email": "hacker@emovers.co.ke",
        "first_name": "Hack",
        "last_name": "Attempt",
        "role": "mover-admin",
        "password": "Admin1234!",
        "password_confirm": "Admin1234!",
    })
    ok(r, 403, "register_staff_forbidden")


def test_logout():
    c = APIClient()
    c.login("staff02@emovers.co.ke", "Staff1234!")
    r = c.post("/api/v1/auth/logout/", {"refresh": c.refresh_token})
    ok(r, 200, "logout")


test("login_admin", test_login_admin)
test("login_staff", test_login_staff)
test("login_bad_password", test_login_bad_password)
test("login_inactive_user", test_login_inactive_user)
test("me_get", test_me_get)
test("me_patch", test_me_patch)
test("me_unauthenticated", test_me_unauthenticated)
test("change_password", test_change_password)
test("register_by_admin", test_register_by_admin)
test("register_by_staff_forbidden", test_register_by_staff_forbidden)
test("logout", test_logout)

# ===========================================================================
# 2. USERS
# ===========================================================================
print("\n--- USERS ---")


def test_user_list():
    r = admin_client.get("/api/v1/users/")
    body = ok(r, 200, "user_list")
    assert "results" in body or isinstance(body, list)


def test_user_list_filter_role():
    r = admin_client.get("/api/v1/users/?role=mover-staff")
    ok(r, 200, "user_list_filter")


def test_user_list_forbidden_staff():
    r = staff_client.get("/api/v1/users/")
    ok(r, 403, "user_list_staff_forbidden")


def test_available_staff():
    r = admin_client.get("/api/v1/users/available-staff/")
    ok(r, 200, "available_staff")


def test_user_detail():
    from accounts.models import User
    u = User.objects.filter(role="mover-staff").first()
    r = admin_client.get(f"/api/v1/users/{u.pk}/")
    ok(r, 200, "user_detail")


def test_user_soft_delete():
    from accounts.models import User
    u = User.objects.filter(email="newstaff@emovers.co.ke").first()
    r = admin_client.delete(f"/api/v1/users/{u.pk}/")
    ok(r, 200, "user_soft_delete")
    u.refresh_from_db()
    assert not u.is_active


def test_staff_profile_get():
    from accounts.models import User
    u = User.objects.filter(role="mover-staff", is_active=True).first()
    r = admin_client.get(f"/api/v1/users/{u.pk}/staff-profile/")
    ok(r, 200, "staff_profile_get")


def test_staff_profile_patch():
    from accounts.models import User
    u = User.objects.filter(role="mover-staff", is_active=True).first()
    r = admin_client.patch(f"/api/v1/users/{u.pk}/staff-profile/", {"notes": "Good worker"})
    ok(r, 200, "staff_profile_patch")


test("user_list", test_user_list)
test("user_list_filter_role", test_user_list_filter_role)
test("user_list_forbidden_staff", test_user_list_forbidden_staff)
test("available_staff", test_available_staff)
test("user_detail", test_user_detail)
test("user_soft_delete", test_user_soft_delete)
test("staff_profile_get", test_staff_profile_get)
test("staff_profile_patch", test_staff_profile_patch)

# ===========================================================================
# 3. CUSTOMERS
# ===========================================================================
print("\n--- CUSTOMERS ---")


def test_customer_create():
    r = admin_client.post("/api/v1/customers/", {
        "first_name": "Test",
        "last_name": "Customer",
        "email": "test.customer@test.com",
        "phone": "+254799111001",
        "address": "Test Street, Nairobi",
    })
    ok(r, 201, "customer_create")


def test_customer_list_admin():
    r = admin_client.get("/api/v1/customers/")
    ok(r, 200, "customer_list_admin")


def test_customer_list_staff():
    r = staff_client.get("/api/v1/customers/")
    ok(r, 200, "customer_list_staff")


def test_customer_search():
    r = admin_client.get("/api/v1/customers/?search=Alice")
    body = ok(r, 200, "customer_search")


def test_customer_detail():
    from customers.models import Customer
    c = Customer.objects.first()
    r = admin_client.get(f"/api/v1/customers/{c.pk}/")
    ok(r, 200, "customer_detail")


def test_customer_update():
    from customers.models import Customer
    c = Customer.objects.first()
    r = admin_client.patch(f"/api/v1/customers/{c.pk}/", {"phone": "+254799000099"})
    ok(r, 200, "customer_update")


def test_customer_delete_with_active_job_blocked():
    from customers.models import Customer
    from jobs.models import Job
    # Find a customer with an active (non-completed) job
    job = Job.objects.filter(
        status__in=["pending", "assigned", "in_progress"]
    ).select_related("customer").first()
    if job:
        r = admin_client.delete(f"/api/v1/customers/{job.customer.pk}/")
        ok(r, 400, "customer_delete_blocked")


def test_customer_create_forbidden_staff():
    r = staff_client.post("/api/v1/customers/", {
        "first_name": "No",
        "last_name": "Access",
        "email": "noaccess@test.com",
        "phone": "+254799000000",
        "address": "Nowhere",
    })
    ok(r, 403, "customer_create_forbidden")


test("customer_create", test_customer_create)
test("customer_list_admin", test_customer_list_admin)
test("customer_list_staff", test_customer_list_staff)
test("customer_search", test_customer_search)
test("customer_detail", test_customer_detail)
test("customer_update", test_customer_update)
test("customer_delete_with_active_job_blocked", test_customer_delete_with_active_job_blocked)
test("customer_create_forbidden_staff", test_customer_create_forbidden_staff)

# ===========================================================================
# 4. FLEET
# ===========================================================================
print("\n--- FLEET ---")


def test_truck_create():
    r = admin_client.post("/api/v1/fleet/", {
        "plate_number": "KCA 999Z",
        "truck_type": "medium",
        "make": "Toyota",
        "model": "Dyna",
        "year": 2020,
        "color": "Red",
        "capacity_tons": "3.00",
        "status": "available",
    })
    ok(r, 201, "truck_create")


def test_truck_list():
    r = admin_client.get("/api/v1/fleet/")
    ok(r, 200, "truck_list")


def test_truck_list_filter_status():
    r = admin_client.get("/api/v1/fleet/?status=available")
    ok(r, 200, "truck_filter_status")


def test_available_trucks():
    r = admin_client.get("/api/v1/fleet/available/")
    ok(r, 200, "available_trucks")


def test_truck_detail():
    from fleet.models import Truck
    t = Truck.objects.first()
    r = admin_client.get(f"/api/v1/fleet/{t.pk}/")
    ok(r, 200, "truck_detail")


def test_truck_update():
    from fleet.models import Truck
    t = Truck.objects.filter(status="available").first()
    r = admin_client.patch(f"/api/v1/fleet/{t.pk}/", {"notes": "Needs oil change soon"})
    ok(r, 200, "truck_update")


def test_truck_delete_on_job_blocked():
    from fleet.models import Truck
    t = Truck.objects.filter(status="on_job").first()
    if t:
        r = admin_client.delete(f"/api/v1/fleet/{t.pk}/")
        ok(r, 400, "truck_delete_blocked")


def test_truck_create_forbidden_staff():
    r = staff_client.post("/api/v1/fleet/", {
        "plate_number": "KCA 888X",
        "truck_type": "small",
        "make": "Isuzu",
        "model": "NKR",
        "year": 2020,
        "capacity_tons": "1.00",
    })
    ok(r, 403, "truck_create_forbidden")


test("truck_create", test_truck_create)
test("truck_list", test_truck_list)
test("truck_list_filter_status", test_truck_list_filter_status)
test("available_trucks", test_available_trucks)
test("truck_detail", test_truck_detail)
test("truck_update", test_truck_update)
test("truck_delete_on_job_blocked", test_truck_delete_on_job_blocked)
test("truck_create_forbidden_staff", test_truck_create_forbidden_staff)

# ===========================================================================
# 5. JOBS
# ===========================================================================
print("\n--- JOBS ---")

from customers.models import Customer
_customer = Customer.objects.filter(email="test.customer@test.com").first()
_new_job_id = None


def test_job_create():
    global _new_job_id
    r = admin_client.post("/api/v1/jobs/", {
        "title": "Integration Test Move",
        "customer": _customer.pk,
        "move_size": "one_bedroom",
        "pickup_address": "Test Pickup St, Nairobi",
        "dropoff_address": "Test Dropoff St, Nairobi",
        "estimated_distance_km": "10.00",
        "scheduled_date": "2025-12-01",
        "requested_staff_count": 5,
        "requested_truck_count": 1,
    })
    body = ok(r, 201, "job_create")
    _new_job_id = body["id"]


def test_job_list():
    r = admin_client.get("/api/v1/jobs/")
    ok(r, 200, "job_list")


def test_job_list_filter_status():
    r = admin_client.get("/api/v1/jobs/?status=pending")
    ok(r, 200, "job_list_filter")


def test_job_list_date_range():
    r = admin_client.get("/api/v1/jobs/?scheduled_date_after=2025-01-01&scheduled_date_before=2025-12-31")
    ok(r, 200, "job_list_date_range")


def test_unassigned_jobs():
    r = admin_client.get("/api/v1/jobs/unassigned/")
    body = ok(r, 200, "unassigned_jobs")
    # Both seeded unassigned jobs should appear
    count = body.get("count", len(body)) if isinstance(body, dict) else len(body)
    results = body.get("results", body)
    assert len(results) >= 2, f"Expected >= 2 unassigned jobs, got {len(results)}"


def test_job_detail():
    r = admin_client.get(f"/api/v1/jobs/{_new_job_id}/")
    body = ok(r, 200, "job_detail")
    has_keys(body, "id", "title", "status", "assignments", "trucks", label="job_detail")


def test_job_update():
    r = admin_client.patch(f"/api/v1/jobs/{_new_job_id}/", {"notes": "Updated notes"})
    ok(r, 200, "job_update")


def _release_all_for_testing():
    """
    Temporarily free all staff profiles and trucks so auto-allocation
    tests have a clean pool to draw from.
    The seeded ASSIGNED / IN_PROGRESS jobs are already saved to the DB
    with their status — releasing resources here only affects availability
    flags, not the job records themselves.
    """
    from accounts.models import StaffProfile
    from fleet.models import Truck as TruckModel
    StaffProfile.objects.all().update(is_available=True)
    TruckModel.objects.filter(status="on_job").update(status=TruckModel.Status.AVAILABLE)


def test_job_auto_allocate():
    _release_all_for_testing()
    r = admin_client.post(f"/api/v1/jobs/{_new_job_id}/auto-allocate/", {
        "num_movers": 3,
        "num_trucks": 1,
    })
    body = ok(r, 200, "job_auto_allocate")
    has_keys(body, "job", label="auto_allocate")
    job_data = body["job"]
    assert job_data["status"] == "assigned"
    assert job_data["assigned_staff_count"] == 4  # 1 supervisor + 3 movers
    assert job_data["assigned_truck_count"] == 1


def test_job_auto_allocate_re_run():
    """Auto-allocate is idempotent — re-running should succeed and re-assign."""
    r = admin_client.post(f"/api/v1/jobs/{_new_job_id}/auto-allocate/", {
        "num_movers": 2,
        "num_trucks": 1,
    })
    body = ok(r, 200, "job_auto_allocate_rerun")
    assert body["job"]["assigned_staff_count"] == 3  # 1 supervisor + 2 movers


def test_job_update_blocked_after_complete():
    from jobs.models import Job
    completed = Job.objects.filter(status="completed").first()
    if completed:
        r = admin_client.patch(f"/api/v1/jobs/{completed.pk}/", {"notes": "Should fail"})
        ok(r, 400, "job_update_blocked")


def test_job_status_start():
    r = admin_client.post(f"/api/v1/jobs/{_new_job_id}/status/", {"action": "start"})
    body = ok(r, 200, "job_status_start")
    assert body["job"]["status"] == "in_progress"


def test_job_status_complete():
    r = admin_client.post(f"/api/v1/jobs/{_new_job_id}/status/", {"action": "complete"})
    body = ok(r, 200, "job_status_complete")
    assert body["job"]["status"] == "completed"


def test_job_status_invalid_transition():
    r = admin_client.post(f"/api/v1/jobs/{_new_job_id}/status/", {"action": "start"})
    ok(r, 400, "job_status_invalid_transition")


def test_job_cancel():
    # Create a new pending job and cancel it
    r = admin_client.post("/api/v1/jobs/", {
        "title": "Cancel Test Move",
        "customer": _customer.pk,
        "move_size": "studio",
        "pickup_address": "A, Nairobi",
        "dropoff_address": "B, Nairobi",
        "estimated_distance_km": "5.00",
        "scheduled_date": "2025-12-02",
    })
    cancel_id = r.json()["id"]
    r = admin_client.post(f"/api/v1/jobs/{cancel_id}/status/", {"action": "cancel"})
    body = ok(r, 200, "job_cancel")
    assert body["job"]["status"] == "cancelled"


def test_job_staff_cannot_cancel():
    # Staff should not be able to cancel a job
    from jobs.models import Job
    job = Job.objects.filter(status="assigned").first()
    if job:
        r = staff_client.post(f"/api/v1/jobs/{job.pk}/status/", {"action": "cancel"})
        ok(r, 403, "staff_cannot_cancel")


def test_job_delete_pending():
    r = admin_client.post("/api/v1/jobs/", {
        "title": "Delete Test Move",
        "customer": _customer.pk,
        "move_size": "studio",
        "pickup_address": "X",
        "dropoff_address": "Y",
        "estimated_distance_km": "1.00",
        "scheduled_date": "2025-12-03",
    })
    delete_id = r.json()["id"]
    r = admin_client.delete(f"/api/v1/jobs/{delete_id}/")
    ok(r, 200, "job_delete_pending")


def test_job_delete_completed_blocked():
    from jobs.models import Job
    completed = Job.objects.filter(status="completed").first()
    if completed:
        r = admin_client.delete(f"/api/v1/jobs/{completed.pk}/")
        ok(r, 400, "job_delete_completed_blocked")


test("job_create", test_job_create)
test("job_list", test_job_list)
test("job_list_filter_status", test_job_list_filter_status)
test("job_list_date_range", test_job_list_date_range)
test("unassigned_jobs", test_unassigned_jobs)
test("job_detail", test_job_detail)
test("job_update", test_job_update)
test("job_auto_allocate", test_job_auto_allocate)
test("job_auto_allocate_re_run", test_job_auto_allocate_re_run)
test("job_update_blocked_after_complete", test_job_update_blocked_after_complete)
test("job_status_start", test_job_status_start)
test("job_status_complete", test_job_status_complete)
test("job_status_invalid_transition", test_job_status_invalid_transition)
test("job_cancel", test_job_cancel)
test("job_staff_cannot_cancel", test_job_staff_cannot_cancel)
test("job_delete_pending", test_job_delete_pending)
test("job_delete_completed_blocked", test_job_delete_completed_blocked)

# ===========================================================================
# 6. BILLING
# ===========================================================================
print("\n--- BILLING ---")

from jobs.models import Job

_completed_job = Job.objects.filter(status="completed", title="Integration Test Move").first()
_invoice_id = None


def test_invoice_generate():
    global _invoice_id
    r = admin_client.post("/api/v1/billing/invoices/generate/", {
        "job_id": _new_job_id,
        "due_date": "2025-12-31",
        "notes": "Integration test invoice",
    })
    body = ok(r, 201, "invoice_generate")
    has_keys(body, "id", "total_amount", "balance_due", "payment_status", label="invoice")
    assert body["payment_status"] == "unpaid"
    assert float(body["base_charge"]) == 2000.0
    _invoice_id = body["id"]


def test_invoice_generate_cost_formula():
    """Verify the cost formula: base + distance + staff + truck + 16% VAT"""
    from billing.models import Invoice
    inv = Invoice.objects.get(pk=_invoice_id)
    expected_base = 2000
    # The job has distance=10km, 3 staff (1 sup + 2 movers), 1 truck (after re-run)
    expected_distance = 100 * 10
    expected_staff = 500 * inv.job.assignments.count()
    expected_truck = 1500 * inv.job.job_trucks.count()
    expected_subtotal = expected_base + expected_distance + expected_staff + expected_truck
    expected_tax = expected_subtotal * 0.16
    expected_total = expected_subtotal + expected_tax
    assert abs(float(inv.total_amount) - expected_total) < 0.01, (
        f"Cost formula mismatch: expected {expected_total}, got {inv.total_amount}"
    )


def test_invoice_list():
    r = admin_client.get("/api/v1/billing/invoices/")
    ok(r, 200, "invoice_list")


def test_invoice_detail():
    r = admin_client.get(f"/api/v1/billing/invoices/{_invoice_id}/")
    body = ok(r, 200, "invoice_detail")
    has_keys(body, "payments", "total_amount", label="invoice_detail")


def test_invoice_update():
    r = admin_client.patch(f"/api/v1/billing/invoices/{_invoice_id}/", {
        "notes": "Updated billing note"
    })
    ok(r, 200, "invoice_update")


def test_simulate_payment_partial():
    from billing.models import Invoice
    inv = Invoice.objects.get(pk=_invoice_id)
    partial = float(inv.total_amount) / 2
    r = admin_client.post(f"/api/v1/billing/invoices/{_invoice_id}/pay/", {
        "amount": str(round(partial, 2)),
        "method": "mpesa",
        "notes": "Partial payment",
    })
    body = ok(r, 201, "payment_partial")
    has_keys(body, "payment", "invoice", label="payment_partial")
    assert body["payment"]["status"] == "completed"
    assert "SIM-MPE" in body["payment"]["transaction_id"]
    assert body["invoice"]["payment_status"] == "partial"


def test_simulate_payment_remainder():
    from billing.models import Invoice
    inv = Invoice.objects.get(pk=_invoice_id)
    r = admin_client.post(f"/api/v1/billing/invoices/{_invoice_id}/pay/", {
        "amount": str(inv.balance_due),
        "method": "cash",
    })
    body = ok(r, 201, "payment_remainder")
    assert body["invoice"]["payment_status"] == "paid"
    assert float(body["invoice"]["balance_due"]) == 0.0


def test_simulate_payment_on_paid_invoice_blocked():
    r = admin_client.post(f"/api/v1/billing/invoices/{_invoice_id}/pay/", {
        "amount": "100.00",
        "method": "cash",
    })
    ok(r, 400, "payment_blocked_on_paid")


def test_simulate_payment_overpay_blocked():
    from billing.models import Invoice
    inv = Invoice.objects.filter(payment_status="unpaid").first()
    if inv:
        r = admin_client.post(f"/api/v1/billing/invoices/{inv.pk}/pay/", {
            "amount": str(float(inv.balance_due) + 9999),
            "method": "card",
        })
        ok(r, 400, "payment_overpay_blocked")


def test_payment_list():
    r = admin_client.get("/api/v1/billing/payments/")
    ok(r, 200, "payment_list")


def test_payment_list_filter_method():
    r = admin_client.get("/api/v1/billing/payments/?method=mpesa")
    ok(r, 200, "payment_filter")


test("invoice_generate", test_invoice_generate)
test("invoice_generate_cost_formula", test_invoice_generate_cost_formula)
test("invoice_list", test_invoice_list)
test("invoice_detail", test_invoice_detail)
test("invoice_update", test_invoice_update)
test("simulate_payment_partial", test_simulate_payment_partial)
test("simulate_payment_remainder", test_simulate_payment_remainder)
test("simulate_payment_on_paid_invoice_blocked", test_simulate_payment_on_paid_invoice_blocked)
test("simulate_payment_overpay_blocked", test_simulate_payment_overpay_blocked)
test("payment_list", test_payment_list)
test("payment_list_filter_method", test_payment_list_filter_method)

# ===========================================================================
# 7. REVIEWS
# ===========================================================================
print("\n--- REVIEWS ---")

from jobs.models import Job as _Job
_completed = _Job.objects.filter(status="completed").exclude(
    title="Integration Test Move"
).first()


def test_review_create_single():
    from jobs.models import JobAssignment
    if not _completed:
        return
    supervisor_assignment = _completed.assignments.filter(
        role=JobAssignment.Role.SUPERVISOR
    ).select_related("staff").first()
    mover_assignment = _completed.assignments.filter(
        role=JobAssignment.Role.MOVER
    ).select_related("staff").first()
    if not (supervisor_assignment and mover_assignment):
        return

    sup_client = APIClient()
    sup_client.login(supervisor_assignment.staff.email, "Staff1234!")
    r = sup_client.post("/api/v1/reviews/create/", {
        "job_id": _completed.pk,
        "reviewee_id": mover_assignment.staff.pk,
        "category": "communication",
        "rating": 4,
        "comment": "Good communicator.",
    })
    ok(r, 201, "review_create_single")


def test_review_bulk_create():
    from jobs.models import Job, JobAssignment
    completed = _Job.objects.filter(
        status="completed", title="Integration Test Move"
    ).first()
    if not completed:
        return
    supervisor_assignment = completed.assignments.filter(
        role=JobAssignment.Role.SUPERVISOR
    ).select_related("staff").first()
    movers = list(
        completed.assignments.filter(role=JobAssignment.Role.MOVER)
        .select_related("staff")[:2]
    )
    if not supervisor_assignment or not movers:
        return

    sup_client = APIClient()
    sup_client.login(supervisor_assignment.staff.email, "Staff1234!")
    r = sup_client.post("/api/v1/reviews/bulk-create/", {
        "job_id": completed.pk,
        "reviews": [
            {"reviewee_id": movers[0].staff.pk, "category": "overall", "rating": 5, "comment": "Top mover."},
            {"reviewee_id": movers[0].staff.pk, "category": "punctuality", "rating": 4},
            {"reviewee_id": movers[1].staff.pk, "category": "overall", "rating": 3},
        ] if len(movers) >= 2 else [
            {"reviewee_id": movers[0].staff.pk, "category": "overall", "rating": 5},
        ],
    })
    body = ok(r, 201, "review_bulk_create")
    has_keys(body, "created", "errors", "summary", label="bulk_review")
    assert body["summary"]["created"] > 0


def test_review_duplicate_blocked():
    """Submitting the same (job, reviewee, category) again should return an error."""
    from reviews.models import StaffReview
    from jobs.models import JobAssignment
    review = StaffReview.objects.first()
    if not review:
        return
    supervisor_assignment = review.job.assignments.filter(
        role=JobAssignment.Role.SUPERVISOR
    ).select_related("staff").first()
    if not supervisor_assignment:
        return
    sup_client = APIClient()
    sup_client.login(supervisor_assignment.staff.email, "Staff1234!")
    r = sup_client.post("/api/v1/reviews/create/", {
        "job_id": review.job.pk,
        "reviewee_id": review.reviewee.pk,
        "category": review.category,
        "rating": 3,
    })
    ok(r, 400, "review_duplicate_blocked")


def test_review_non_supervisor_blocked():
    """A non-supervisor staff member cannot submit reviews."""
    from jobs.models import JobAssignment
    if not _completed:
        return
    mover_assignment = _completed.assignments.filter(
        role=JobAssignment.Role.MOVER
    ).select_related("staff").first()
    if not mover_assignment:
        return
    mover_client = APIClient()
    mover_client.login(mover_assignment.staff.email, "Staff1234!")
    r = mover_client.post("/api/v1/reviews/create/", {
        "job_id": _completed.pk,
        "reviewee_id": mover_assignment.staff.pk,
        "category": "overall",
        "rating": 5,
    })
    ok(r, 400, "non_supervisor_blocked")


def test_review_list_admin():
    r = admin_client.get("/api/v1/reviews/")
    ok(r, 200, "review_list_admin")


def test_my_reviews():
    r = staff_client.get("/api/v1/reviews/my-reviews/")
    ok(r, 200, "my_reviews")


def test_review_list_admin_only():
    r = staff_client.get("/api/v1/reviews/")
    ok(r, 403, "review_list_admin_only")


def test_staff_review_summary():
    from accounts.models import User
    staff = User.objects.filter(role="mover-staff").first()
    r = admin_client.get(f"/api/v1/reviews/staff/{staff.pk}/summary/")
    body = ok(r, 200, "staff_review_summary")
    has_keys(body, "staff_id", "average_rating", "recommendation_score", "category_breakdown", label="summary")


def test_recommendation_score_updated():
    """After reviews, recommendation_score should have changed from default 1.0 for rated staff."""
    from accounts.models import StaffProfile
    from reviews.models import StaffReview
    reviewed_staff_ids = StaffReview.objects.values_list("reviewee_id", flat=True).distinct()
    profiles = StaffProfile.objects.filter(user_id__in=reviewed_staff_ids)
    for p in profiles:
        assert p.total_reviews > 0, f"Staff {p.user_id} has reviews but total_reviews=0"
        assert 0.2 <= float(p.recommendation_score) <= 1.0, (
            f"Score {p.recommendation_score} out of expected range [0.2, 1.0]"
        )


def test_job_reviews():
    if not _completed:
        return
    r = admin_client.get(f"/api/v1/reviews/job/{_completed.pk}/")
    ok(r, 200, "job_reviews")


test("review_create_single", test_review_create_single)
test("review_bulk_create", test_review_bulk_create)
test("review_duplicate_blocked", test_review_duplicate_blocked)
test("review_non_supervisor_blocked", test_review_non_supervisor_blocked)
test("review_list_admin", test_review_list_admin)
test("my_reviews", test_my_reviews)
test("review_list_admin_only", test_review_list_admin_only)
test("staff_review_summary", test_staff_review_summary)
test("recommendation_score_updated", test_recommendation_score_updated)
test("job_reviews", test_job_reviews)

# ===========================================================================
# 8. REPORTS
# ===========================================================================
print("\n--- REPORTS ---")


def test_report_dashboard():
    r = admin_client.get("/api/v1/reports/dashboard/")
    body = ok(r, 200, "report_dashboard")
    has_keys(body, "staff", "fleet", "jobs", "billing", "customers", label="dashboard")
    has_keys(body["jobs"], "total", "completed", "unassigned_needing_attention", label="dashboard_jobs")


def test_report_dashboard_custom_window():
    r = admin_client.get("/api/v1/reports/dashboard/?days=7")
    body = ok(r, 200, "report_dashboard_7days")
    assert body["window_days"] == 7


def test_report_jobs():
    r = admin_client.get("/api/v1/reports/jobs/?days=90")
    body = ok(r, 200, "report_jobs")
    has_keys(body, "status_breakdown", "move_size_distribution", "daily_completions", label="report_jobs")


def test_report_billing():
    r = admin_client.get("/api/v1/reports/billing/")
    body = ok(r, 200, "report_billing")
    has_keys(body, "revenue_totals", "payment_method_breakdown", "monthly_revenue_trend", label="billing_report")
    assert float(body["revenue_totals"]["total_invoiced"]) > 0


def test_report_staff_performance():
    r = admin_client.get("/api/v1/reports/staff-performance/")
    body = ok(r, 200, "report_staff_perf")
    has_keys(body, "total_staff", "staff", label="staff_perf")
    staff_list = body["staff"]
    assert len(staff_list) > 0
    # Should be sorted by recommendation_score descending
    scores = [s["recommendation_score"] for s in staff_list]
    assert scores == sorted(scores, reverse=True), "Staff not sorted by recommendation_score DESC"


def test_report_staff_performance_available_only():
    r = admin_client.get("/api/v1/reports/staff-performance/?available_only=true")
    ok(r, 200, "report_staff_perf_available")


def test_report_fleet():
    r = admin_client.get("/api/v1/reports/fleet/")
    body = ok(r, 200, "report_fleet")
    has_keys(body, "total_trucks", "utilization_rate_percent", "status_breakdown", label="fleet_report")
    assert body["total_trucks"] > 0


def test_reports_forbidden_staff():
    for url in [
        "/api/v1/reports/dashboard/",
        "/api/v1/reports/jobs/",
        "/api/v1/reports/billing/",
        "/api/v1/reports/staff-performance/",
        "/api/v1/reports/fleet/",
    ]:
        r = staff_client.get(url)
        assert r.status_code == 403, f"Expected 403 for staff on {url}, got {r.status_code}"


test("report_dashboard", test_report_dashboard)
test("report_dashboard_custom_window", test_report_dashboard_custom_window)
test("report_jobs", test_report_jobs)
test("report_billing", test_report_billing)
test("report_staff_performance", test_report_staff_performance)
test("report_staff_performance_available_only", test_report_staff_performance_available_only)
test("report_fleet", test_report_fleet)
test("reports_forbidden_staff", test_reports_forbidden_staff)

# ===========================================================================
# 9. JOB APPLICATION FLOW
# ===========================================================================
print("\n--- JOB APPLICATION FLOW ---")

from jobs.models import Job as _AppJob, JobApplication
from accounts.models import User as _AppUser

# Create a fresh pending job for the application flow tests
_app_job_id = None
_app_staff_ids = []

def test_app_flow_setup():
    global _app_job_id, _app_staff_ids
    from customers.models import Customer
    cust = Customer.objects.first()
    r = admin_client.post("/api/v1/jobs/", {
        "title": "Application Flow Test Move",
        "customer": cust.pk,
        "move_size": "studio",
        "pickup_address": "Test St 1",
        "dropoff_address": "Test St 2",
        "estimated_distance_km": "3.00",
        "scheduled_date": "2026-06-01",
        "max_applicants": 10,
    })
    body = ok(r, 201, "app_flow_setup")
    _app_job_id = body["id"]
    # Collect some staff PKs from seed data
    staff_qs = _AppUser.objects.filter(role="mover-staff", is_active=True)[:5]
    _app_staff_ids = list(staff_qs.values_list("pk", flat=True))


def test_staff_apply_for_job():
    r = staff_client.post(f"/api/v1/jobs/{_app_job_id}/apply/")
    body = ok(r, 201, "staff_apply")
    has_keys(body, "application", label="staff_apply")
    assert body["application"]["status"] == "applied"


def test_staff_apply_duplicate_blocked():
    r = staff_client.post(f"/api/v1/jobs/{_app_job_id}/apply/")
    ok(r, 400, "staff_apply_duplicate_blocked")


def test_admin_sees_applications():
    r = admin_client.get(f"/api/v1/jobs/{_app_job_id}/applications/")
    body = ok(r, 200, "admin_sees_applications")
    assert isinstance(body["results"] if "results" in body else body, (list, dict))


def test_my_applications_staff():
    r = staff_client.get("/api/v1/jobs/my-applications/")
    body = ok(r, 200, "my_applications_staff")
    results = body.get("results", body) if isinstance(body, dict) else body
    assert len(results) >= 1


def test_staff_withdraw_application():
    # First apply with a fresh staff client
    from accounts.models import User
    another_staff = User.objects.filter(role="mover-staff", is_active=True).exclude(
        email="staff01@emovers.co.ke"
    ).first()
    if not another_staff:
        return
    c2 = APIClient()
    c2.login(another_staff.email, "Staff1234!")
    c2.post(f"/api/v1/jobs/{_app_job_id}/apply/")
    r = c2.delete(f"/api/v1/jobs/{_app_job_id}/apply/")
    body = ok(r, 200, "staff_withdraw")
    assert body["application"]["status"] == "withdrawn"


def test_admin_approve_applications():
    from accounts.models import User
    # Make sure there's at least one APPLIED application to approve
    applied = JobApplication.objects.filter(
        job_id=_app_job_id, status="applied"
    ).select_related("staff")
    if not applied.exists():
        # Apply with admin as a workaround — normally admin doesn't apply, but let's ensure state
        return
    first_app = applied.first()
    r = admin_client.post(f"/api/v1/jobs/{_app_job_id}/approve-applications/", {
        "approved_staff_ids": [first_app.staff_id],
        "supervisor_id": first_app.staff_id,
    })
    body = ok(r, 200, "admin_approve_applications")
    assert body["job"]["status"] == "assigned"


def test_supervisor_mismatch_blocked():
    # Create another job for this test
    from customers.models import Customer
    cust = Customer.objects.first()
    r = admin_client.post("/api/v1/jobs/", {
        "title": "Supervisor Mismatch Test",
        "customer": cust.pk,
        "move_size": "studio",
        "pickup_address": "A", "dropoff_address": "B",
        "estimated_distance_km": "1.00",
        "scheduled_date": "2026-07-01",
    })
    jid = r.json()["id"]
    from accounts.models import User
    staff = User.objects.filter(role="mover-staff", is_active=True).first()
    staff_client2 = APIClient()
    staff_client2.login(staff.email, "Staff1234!")
    staff_client2.post(f"/api/v1/jobs/{jid}/apply/")
    # Pass a supervisor_id not in the approved list
    r = admin_client.post(f"/api/v1/jobs/{jid}/approve-applications/", {
        "approved_staff_ids": [staff.pk],
        "supervisor_id": 99999,  # not in list
    })
    ok(r, 400, "supervisor_mismatch_blocked")


test("app_flow_setup", test_app_flow_setup)
test("staff_apply_for_job", test_staff_apply_for_job)
test("staff_apply_duplicate_blocked", test_staff_apply_duplicate_blocked)
test("admin_sees_applications", test_admin_sees_applications)
test("my_applications_staff", test_my_applications_staff)
test("staff_withdraw_application", test_staff_withdraw_application)
test("admin_approve_applications", test_admin_approve_applications)
test("supervisor_mismatch_blocked", test_supervisor_mismatch_blocked)

# ===========================================================================
# 10. NOTIFICATIONS
# ===========================================================================
print("\n--- NOTIFICATIONS ---")


def test_notification_list():
    r = staff_client.get("/api/v1/notifications/")
    ok(r, 200, "notification_list")


def test_notification_unread_count():
    r = staff_client.get("/api/v1/notifications/unread-count/")
    body = ok(r, 200, "notification_unread_count")
    has_keys(body, "count", label="unread_count")
    assert isinstance(body["count"], int)


def test_notification_mark_all_read():
    r = staff_client.post("/api/v1/notifications/mark-all-read/")
    body = ok(r, 200, "notification_mark_all_read")
    has_keys(body, "message", label="mark_all_read")


def test_notification_unread_count_zero_after_mark_all():
    r = staff_client.get("/api/v1/notifications/unread-count/")
    body = ok(r, 200, "notification_count_after_mark")
    assert body["count"] == 0, f"Expected 0 unread, got {body['count']}"


def test_notification_mark_single_read():
    # Create a notification first
    from notifications.models import Notification
    from accounts.models import User
    staff = User.objects.get(email="staff01@emovers.co.ke")
    n = Notification.objects.create(
        recipient=staff,
        notification_type="general",
        title="Test",
        body="Test notification",
        is_read=False,
    )
    r = staff_client.patch(f"/api/v1/notifications/{n.pk}/read/")
    body = ok(r, 200, "notification_mark_single")
    assert body["is_read"] is True


def test_notification_other_user_blocked():
    from notifications.models import Notification
    from accounts.models import User
    # Create a notification for admin, try to mark it as read with staff client
    admin = User.objects.get(email="admin@emovers.co.ke")
    n = Notification.objects.create(
        recipient=admin,
        notification_type="general",
        title="Admin notification",
        body="Not for staff",
        is_read=False,
    )
    r = staff_client.patch(f"/api/v1/notifications/{n.pk}/read/")
    ok(r, 404, "notification_other_user_blocked")


def test_notification_filter_unread():
    r = staff_client.get("/api/v1/notifications/?is_read=false")
    ok(r, 200, "notification_filter_unread")


test("notification_list", test_notification_list)
test("notification_unread_count", test_notification_unread_count)
test("notification_mark_all_read", test_notification_mark_all_read)
test("notification_unread_count_zero_after_mark_all", test_notification_unread_count_zero_after_mark_all)
test("notification_mark_single_read", test_notification_mark_single_read)
test("notification_other_user_blocked", test_notification_other_user_blocked)
test("notification_filter_unread", test_notification_filter_unread)

# ===========================================================================
# 11. ATTENDANCE
# ===========================================================================
print("\n--- ATTENDANCE ---")

_att_job = None
_att_pin = None


def test_attendance_setup():
    """Find an ASSIGNED job to use for attendance tests."""
    global _att_job
    _att_job = _AppJob.objects.filter(status="assigned").first()


def test_generate_pin():
    global _att_pin
    if not _att_job:
        return
    r = admin_client.post(f"/api/v1/attendance/generate-pin/{_att_job.pk}/")
    body = ok(r, 200, "generate_pin")
    has_keys(body, "pin", "job_id", label="generate_pin")
    assert len(body["pin"]) == 6
    _att_pin = body["pin"]


def test_generate_pin_wrong_status():
    pending = _AppJob.objects.filter(status="pending").first()
    if not pending:
        return
    r = admin_client.post(f"/api/v1/attendance/generate-pin/{pending.pk}/")
    ok(r, 400, "generate_pin_wrong_status")


def test_confirm_attendance_correct_pin():
    if not (_att_job and _att_pin):
        return
    # Find a staff assigned to this job
    from jobs.models import JobAssignment
    assignment = _att_job.assignments.filter(
        role="mover"
    ).select_related("staff").first()
    if not assignment:
        return
    mover_client = APIClient()
    mover_client.login(assignment.staff.email, "Staff1234!")
    r = mover_client.post("/api/v1/attendance/confirm/", {
        "job_id": _att_job.pk,
        "pin": _att_pin,
    })
    body = ok(r, 201, "confirm_attendance_correct_pin")
    assert body["record"]["status"] == "confirmed"


def test_confirm_attendance_wrong_pin():
    if not _att_job:
        return
    from jobs.models import JobAssignment
    assignment = _att_job.assignments.filter(role="mover").select_related("staff").first()
    if not assignment:
        return
    mover_client = APIClient()
    mover_client.login(assignment.staff.email, "Staff1234!")
    r = mover_client.post("/api/v1/attendance/confirm/", {
        "job_id": _att_job.pk,
        "pin": "000000",
    })
    ok(r, 400, "confirm_attendance_wrong_pin")


def test_attendance_list_for_job():
    if not _att_job:
        return
    r = admin_client.get(f"/api/v1/attendance/{_att_job.pk}/")
    body = ok(r, 200, "attendance_list_for_job")


def test_mark_absent():
    if not _att_job:
        return
    from jobs.models import JobAssignment
    # Find a mover who hasn't confirmed
    from attendance.models import AttendanceRecord
    confirmed_ids = set(
        AttendanceRecord.objects.filter(job=_att_job).values_list("staff_id", flat=True)
    )
    unconfirmed = _att_job.assignments.filter(
        role="mover"
    ).exclude(staff_id__in=confirmed_ids).select_related("staff").first()
    if not unconfirmed:
        return
    r = admin_client.post(f"/api/v1/attendance/{_att_job.pk}/mark-absent/", {
        "staff_id": unconfirmed.staff_id,
        "notes": "Did not arrive",
    })
    body = ok(r, 201, "mark_absent")
    assert body["record"]["status"] == "absent"


test("attendance_setup", test_attendance_setup)
test("generate_pin", test_generate_pin)
test("generate_pin_wrong_status", test_generate_pin_wrong_status)
test("confirm_attendance_correct_pin", test_confirm_attendance_correct_pin)
test("confirm_attendance_wrong_pin", test_confirm_attendance_wrong_pin)
test("attendance_list_for_job", test_attendance_list_for_job)
test("mark_absent", test_mark_absent)

# ===========================================================================
# 12. PAYMENT DISBURSEMENT
# ===========================================================================
print("\n--- DISBURSEMENT ---")


def test_disburse_payment():
    from billing.models import Invoice
    paid_invoice = Invoice.objects.filter(payment_status="paid").first()
    if not paid_invoice:
        return
    r = admin_client.post(f"/api/v1/billing/invoices/{paid_invoice.pk}/disburse/")
    body = ok(r, 201, "disburse_payment")
    has_keys(body, "disbursements", "message", label="disburse")
    assert len(body["disbursements"]) > 0


def test_disburse_payment_idempotent_blocked():
    from billing.models import Invoice
    paid_invoice = Invoice.objects.filter(payment_status="paid").first()
    if not paid_invoice:
        return
    r = admin_client.post(f"/api/v1/billing/invoices/{paid_invoice.pk}/disburse/")
    ok(r, 400, "disburse_idempotent_blocked")


def test_disburse_unpaid_blocked():
    from billing.models import Invoice
    unpaid = Invoice.objects.filter(payment_status="unpaid").first()
    if not unpaid:
        return
    r = admin_client.post(f"/api/v1/billing/invoices/{unpaid.pk}/disburse/")
    ok(r, 400, "disburse_unpaid_blocked")


def test_disbursement_list():
    r = admin_client.get("/api/v1/billing/disbursements/")
    ok(r, 200, "disbursement_list")


test("disburse_payment", test_disburse_payment)
test("disburse_payment_idempotent_blocked", test_disburse_payment_idempotent_blocked)
test("disburse_unpaid_blocked", test_disburse_unpaid_blocked)
test("disbursement_list", test_disbursement_list)

# ===========================================================================
# 13. NEW REPORTS
# ===========================================================================
print("\n--- NEW REPORTS ---")


def test_report_attendance():
    r = admin_client.get("/api/v1/reports/attendance/")
    body = ok(r, 200, "report_attendance")
    has_keys(body, "totals", "per_job", "top_absent_staff", label="att_report")
    has_keys(body["totals"], "total_records", "confirmed", "absent", label="att_totals")


def test_report_applications():
    r = admin_client.get("/api/v1/reports/applications/")
    body = ok(r, 200, "report_applications")
    has_keys(body, "total_applications", "status_breakdown", "approval_rate_percent", label="app_report")


def test_new_reports_forbidden_staff():
    for url in ["/api/v1/reports/attendance/", "/api/v1/reports/applications/"]:
        r = staff_client.get(url)
        assert r.status_code == 403, f"Expected 403 for staff on {url}, got {r.status_code}"


test("report_attendance", test_report_attendance)
test("report_applications", test_report_applications)
test("new_reports_forbidden_staff", test_new_reports_forbidden_staff)

# ===========================================================================
# Summary
# ===========================================================================
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"  Results: {PASS}/{total} passed  |  {FAIL} failed")
print(f"{'='*60}")

if FAIL > 0:
    print("\nFailed tests:")
    for result in RESULTS:
        if result[0] == "FAIL":
            print(f"  FAIL  {result[1]}")
            print(f"         {result[2]}")
    sys.exit(1)
else:
    print("\n  All tests passed.")
    sys.exit(0)
