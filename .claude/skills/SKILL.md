# E-Movers Backend — Django REST Framework SKILL.md

> **Purpose:** This document is the authoritative guide for every developer
> working on the E-Movers backend. It covers architecture decisions, module
> contracts, coding standards, Swagger documentation setup, testing patterns,
> and the complete roadmap for features that are new relative to the current
> codebase. Read this before touching any file.

---

## Table of Contents

1. [Project Overview & Scope](#1-project-overview--scope)
2. [Architecture & Three-Tier Design](#2-architecture--three-tier-design)
3. [Module Map](#3-module-map)
4. [Tech Stack & Dependencies](#4-tech-stack--dependencies)
5. [Environment Setup (Step-by-Step)](#5-environment-setup-step-by-step)
6. [Coding Standards](#6-coding-standards)
7. [App-by-App Contract](#7-app-by-app-contract)
   - 7.1 accounts
   - 7.2 customers
   - 7.3 fleet
   - 7.4 jobs (with new application flow)
   - 7.5 billing
   - 7.6 reviews
   - 7.7 notifications (NEW)
   - 7.8 attendance (NEW)
   - 7.9 reports
8. [New Feature Implementation Guide](#8-new-feature-implementation-guide)
   - 8.1 Job Application Flow
   - 8.2 Admin Approval & Supervisor Selection
   - 8.3 Attendance / Presence Confirmation
   - 8.4 Payment Disbursement Simulation
   - 8.5 Recommendation Engine (Review-Based)
   - 8.6 Notifications
9. [Swagger / OpenAPI Documentation](#9-swagger--openapi-documentation)
10. [Serializer Patterns](#10-serializer-patterns)
11. [Permission Matrix](#11-permission-matrix)
12. [Service Layer Rules](#12-service-layer-rules)
13. [Signal Conventions](#13-signal-conventions)
14. [Error Response Contract](#14-error-response-contract)
15. [Testing Guide](#15-testing-guide)
16. [Database Schema Notes](#16-database-schema-notes)
17. [Seed Data](#17-seed-data)
18. [Deployment Checklist](#18-deployment-checklist)
19. [Changelog & What Is New](#19-changelog--what-is-new)

---

## 1. Project Overview & Scope

**E-Movers** is a moving-company management system. It is **not** a
customer-facing booking platform. It is an internal operational tool used by:

| Actor | Role value | What they do |
|---|---|---|
| Admin | `mover-admin` | Creates jobs, approves applicants, selects supervisors, disburses pay |
| Staff (Mover) | `mover-staff` | Applies for jobs, confirms attendance, receives reviews |

### Business Flow (end-to-end)

```
1.  Admin creates Job (status = pending)
2.  Staff apply for the job (JobApplication, status = applied)
        └─ Deadline OR max-applicant cap closes applications
3.  Admin reviews applicants, approves a subset
        └─ Admin picks ONE supervisor from the approved set
4.  Approved staff receive a success notification
        └─ Notification includes the full team list for that job
5.  Job status → assigned
6.  On moving day, each staff member confirms attendance
        └─ AttendanceRecord created (confirmed / absent)
7.  Job starts → in_progress
8.  Job completes → completed
9.  Supervisor submits reviews for each mover (bulk or single)
        └─ Scores recalculate immediately via signal
10. Admin disburses payment (simulated)
        └─ PaymentDisbursement record per staff member
11. For the NEXT job, application ranking uses recommendation_score
        └─ Score = f(supervisor reviews only), not job count
```

---

## 2. Architecture & Three-Tier Design

```
┌───────────────────────────────────────────┐
│  PRESENTATION LAYER                       │
│  Next.js frontend (separate repo)         │
│  Consumes this API via JWT Bearer tokens  │
└─────────────────────┬─────────────────────┘
                      │ HTTP/JSON
┌─────────────────────▼─────────────────────┐
│  APPLICATION LAYER  (this repo)           │
│  Django 4.2 + Django REST Framework 3.15  │
│  Business logic lives in services.py      │
│  Views are thin — they only parse/respond │
└─────────────────────┬─────────────────────┘
                      │ ORM
┌─────────────────────▼─────────────────────┐
│  DATABASE LAYER                           │
│  SQLite (dev) / PostgreSQL (production)   │
└───────────────────────────────────────────┘
```

### Intra-app dependency rules

```
accounts  ← (no app dependency)
customers ← accounts
fleet     ← accounts
jobs      ← accounts, customers, fleet
billing   ← jobs
reviews   ← jobs, accounts
notifications ← accounts, jobs      (NEW)
attendance    ← jobs, accounts      (NEW)
reports   ← all apps (read-only queries)
```

Never create cross-imports that form a cycle. Use lazy imports inside
functions when a cycle is unavoidable (see `accounts/models.py:
recalculate_scores`).

---

## 3. Module Map

```
e_movers_backend/
├── e_movers/
│   ├── settings.py          # All configuration in one place
│   ├── urls.py              # Root router — prefix api/v1/
│   ├── asgi.py
│   └── wsgi.py
│
├── accounts/                # Users, JWT auth, StaffProfile
│   ├── models.py            # User (AbstractBaseUser), StaffProfile
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py              # api/v1/auth/ + api/v1/users/
│   ├── permissions.py       # IsMoverAdmin, IsMoverStaff, IsAdminOrStaff
│   ├── signals.py           # Auto-create StaffProfile on staff User save
│   ├── admin.py
│   └── apps.py
│
├── customers/               # Customer CRUD
├── fleet/                   # Truck management
│
├── jobs/                    # Core job lifecycle — EXTENDED with application flow
│   ├── models.py            # Job, JobAssignment, JobTruck, JobApplication (NEW)
│   ├── services.py          # auto_allocate, assign_*, transition_status,
│   │                        # apply_for_job, approve_applications (NEW)
│   ├── serializers.py
│   ├── views.py
│   ├── filters.py
│   ├── urls.py
│   ├── signals.py           # NEW — fires notification on approval
│   └── admin.py
│
├── billing/                 # Invoices + simulated payments + disbursements
│   ├── models.py            # Invoice, Payment, PaymentDisbursement (NEW)
│   ├── services.py          # generate_invoice, simulate_payment,
│   │                        # disburse_payment (NEW)
│   ├── serializers.py
│   ├── views.py
│   ├── filters.py
│   └── urls.py
│
├── reviews/                 # Supervisor reviews → score updates
│   ├── models.py            # StaffReview
│   ├── services.py          # create_review, get_staff_review_summary
│   ├── serializers.py
│   ├── views.py
│   ├── signals.py           # Recalculate score on save/delete
│   └── urls.py
│
├── notifications/           # NEW app
│   ├── models.py            # Notification
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
│
├── attendance/              # NEW app
│   ├── models.py            # AttendanceRecord
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
│
├── reports/                 # Aggregated read-only reporting (no models)
│
├── integration_tests.py     # Full end-to-end suite
├── manage.py
├── requirements.txt
└── SKILL.md                 # ← this file
```

---

## 4. Tech Stack & Dependencies

### Current `requirements.txt`

```
Django>=4.2,<5.0
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
django-cors-headers>=4.3
django-filter>=23.5
```

### Add these for new features

```
# Swagger / OpenAPI docs
drf-spectacular>=0.27

# Notification scheduling (optional, for deadline jobs)
django-celery-beat>=2.5        # only if using Celery
celery>=5.3                    # only if using Celery
redis>=5.0                     # only if using Celery

# Dev/test
factory-boy>=3.3
pytest-django>=4.8
```

Install all:

```bash
pip install drf-spectacular factory-boy pytest-django
pip freeze > requirements.txt
```

---

## 5. Environment Setup (Step-by-Step)

### Windows

```powershell
# Clone
git clone <repo>
cd e_movers_backend

# Virtualenv
python -m venv venv
venv\Scripts\activate

# Dependencies
pip install -r requirements.txt

# First-time DB
python manage.py migrate

# Seed
python manage.py seed_data

# Run
python manage.py runserver
```

### macOS / Linux

```bash
git clone <repo>
cd e_movers_backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

### Reset DB (Windows)

```powershell
del db.sqlite3
rmdir /s /q accounts\migrations
rmdir /s /q customers\migrations
rmdir /s /q fleet\migrations
rmdir /s /q jobs\migrations
rmdir /s /q billing\migrations
rmdir /s /q reviews\migrations
rmdir /s /q notifications\migrations
rmdir /s /q attendance\migrations
python manage.py makemigrations accounts customers fleet jobs billing reviews notifications attendance
python manage.py migrate
python manage.py seed_data
```

### Reset DB (Mac/Linux)

```bash
rm db.sqlite3
find . -path "*/migrations/0*.py" -delete
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
```

---

## 6. Coding Standards

### Naming

| Thing | Convention | Example |
|---|---|---|
| Model | PascalCase | `JobApplication` |
| Serializer | PascalCase + `Serializer` | `JobApplicationSerializer` |
| View | PascalCase + `View` | `ApplyForJobView` |
| Service function | snake_case verb-first | `apply_for_job()` |
| Custom exception | PascalCase + `Error` | `ApplicationError` |
| URL name | snake_case | `job_apply` |

### File rules

- **One service function per business action.** Never put business logic in views or serializers.
- **Views are thin.** A view: validates input → calls service → returns Response.
- **Never import a view from another app.** Only import models, serializers, services, permissions.
- **All monetary values** are `DecimalField` with `max_digits=10, decimal_places=2`. Never use float for money.
- **All timestamps** use `auto_now_add=True` (created) or `auto_now=True` (updated). Never set timestamps manually outside of tests.
- **All QuerySets** that will be serialized must call `select_related` / `prefetch_related` to avoid N+1 queries.

### Comment style

Every service function must have a docstring following this template:

```python
def my_service(arg1, arg2):
    """
    One-line summary.

    Extended description of what this does and why.

    Parameters
    ----------
    arg1 : Type
        What it is.
    arg2 : Type
        What it is.

    Returns
    -------
    ModelInstance

    Raises
    ------
    MyError
        When this condition is true.
    """
```

---

## 7. App-by-App Contract

### 7.1 accounts

**Models**

| Model | Purpose |
|---|---|
| `User` | AbstractBaseUser. Fields: email, first_name, last_name, phone, role, is_active |
| `StaffProfile` | OneToOne with User (staff only). Tracks availability, rating, recommendation_score |

**Key properties on `StaffProfile`**

```python
recommendation_score = round((avg_rating / 5.0) * 0.8 + 0.2, 3)
# Range: 0.200 (worst) → 1.000 (best / no reviews yet)
```

**Endpoints**

| Method | URL | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/login/` | Public | JWT login |
| POST | `/api/v1/auth/logout/` | Auth | Blacklist refresh token |
| POST | `/api/v1/auth/token/refresh/` | Public | Rotate access token |
| GET/PATCH | `/api/v1/auth/me/` | Auth | Own profile |
| POST | `/api/v1/auth/change-password/` | Auth | Change own password |
| POST | `/api/v1/auth/register/` | Admin | Create user |
| GET | `/api/v1/users/` | Admin | List all users |
| GET | `/api/v1/users/available-staff/` | Admin | Available staff ranked by score |
| GET/PATCH/DELETE | `/api/v1/users/<id>/` | Admin | User detail (DELETE = soft) |
| GET/PATCH | `/api/v1/users/<id>/staff-profile/` | Admin | Staff profile |

---

### 7.2 customers

**Endpoints**

| Method | URL | Permission | Purpose |
|---|---|---|---|
| GET/POST | `/api/v1/customers/` | GET: Staff+Admin / POST: Admin | CRUD |
| GET/PATCH/DELETE | `/api/v1/customers/<id>/` | Admin | DELETE blocked if active jobs |

---

### 7.3 fleet

**Truck statuses:** `available`, `on_job`, `maintenance`

**Endpoints**

| Method | URL | Permission | Purpose |
|---|---|---|---|
| GET/POST | `/api/v1/fleet/` | GET: Staff+Admin / POST: Admin | CRUD |
| GET | `/api/v1/fleet/available/` | Staff+Admin | Only available trucks |
| GET/PATCH/DELETE | `/api/v1/fleet/<id>/` | Admin | DELETE blocked if `on_job` |

---

### 7.4 jobs (EXTENDED)

#### Existing models

`Job`, `JobAssignment`, `JobTruck`

#### New model: `JobApplication`

```python
class JobApplication(models.Model):
    class Status(models.TextChoices):
        APPLIED   = "applied",   "Applied"
        APPROVED  = "approved",  "Approved"
        REJECTED  = "rejected",  "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job       = ForeignKey(Job, related_name="applications")
    staff     = ForeignKey(User, limit_choices_to={"role": "mover-staff"})
    status    = CharField(choices=Status.choices, default=Status.APPLIED)
    applied_at = DateTimeField(auto_now_add=True)
    reviewed_at = DateTimeField(null=True, blank=True)
    reviewed_by = ForeignKey(User, null=True, related_name="reviewed_applications")
    note      = TextField(blank=True)   # Admin note on approval/rejection

    class Meta:
        unique_together = [("job", "staff")]
```

#### Job model additions

Add to `Job`:

```python
application_deadline = models.DateTimeField(null=True, blank=True)
max_applicants       = models.PositiveSmallIntegerField(default=20)
```

#### Endpoint additions

| Method | URL | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/jobs/<id>/apply/` | Staff | Staff applies for job |
| DELETE | `/api/v1/jobs/<id>/apply/` | Staff | Staff withdraws application |
| GET | `/api/v1/jobs/<id>/applications/` | Admin | List all applicants with scores |
| POST | `/api/v1/jobs/<id>/approve-applications/` | Admin | Approve subset + pick supervisor |
| GET | `/api/v1/jobs/my-applications/` | Staff | Own application history |

#### Application business rules (enforced in `jobs/services.py`)

```
apply_for_job():
  - Job must be PENDING
  - Deadline must not have passed (if set)
  - Max applicants must not be reached
  - Staff must not have already applied
  - Staff must be active (is_active=True)

approve_applications():
  - job must be PENDING
  - All approved staff must have status=APPLIED
  - Exactly ONE supervisor_id must be in the approved set
  - On success:
      → Create JobAssignment for each approved staff
      → Lock StaffProfile.is_available = False
      → Send notifications (success + team list)
      → Rejected applicants get a rejection notification
      → Job status → ASSIGNED
```

---

### 7.5 billing (EXTENDED)

#### Cost formula (unchanged)

```
base_charge     = 2,000 KES
distance_charge = 100 × estimated_distance_km
staff_charge    = 500 × assigned_staff_count
truck_charge    = 1,500 × assigned_truck_count
subtotal        = sum of above
tax_amount      = subtotal × 16%
total_amount    = subtotal + tax_amount
```

#### New model: `PaymentDisbursement`

```python
class PaymentDisbursement(models.Model):
    class Status(models.TextChoices):
        PENDING    = "pending",    "Pending"
        DISBURSED  = "disbursed",  "Disbursed"

    invoice     = ForeignKey(Invoice, related_name="disbursements")
    staff       = ForeignKey(User, related_name="disbursements")
    amount      = DecimalField(max_digits=10, decimal_places=2)
    status      = CharField(choices=Status.choices, default=Status.PENDING)
    disbursed_by = ForeignKey(User, null=True, related_name="made_disbursements")
    disbursed_at = DateTimeField(null=True, blank=True)
    transaction_ref = CharField(max_length=100, unique=True)
    notes        = TextField(blank=True)

    class Meta:
        unique_together = [("invoice", "staff")]
```

#### New endpoint

| Method | URL | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/billing/invoices/<id>/disburse/` | Admin | Simulate pay disbursement to each staff member |
| GET | `/api/v1/billing/disbursements/` | Admin | List all disbursement records |

#### Disbursement logic

```python
def disburse_payment(invoice, disbursed_by):
    """
    Split the collected amount equally among all assigned staff
    and create one PaymentDisbursement record per staff member.
    Uses SIM-DSB-<timestamp>-<hex> as transaction_ref.
    Only callable once per invoice (idempotent check).
    """
```

---

### 7.6 reviews

No model changes. See Section 8 for new recommendation logic details.

---

### 7.7 notifications (NEW app)

#### Model

```python
class Notification(models.Model):
    class Type(models.TextChoices):
        APPLICATION_APPROVED  = "application_approved"
        APPLICATION_REJECTED  = "application_rejected"
        JOB_TEAM_ANNOUNCED    = "job_team_announced"
        ATTENDANCE_REMINDER   = "attendance_reminder"
        PAYMENT_DISBURSED     = "payment_disbursed"
        REVIEW_RECEIVED       = "review_received"
        GENERAL               = "general"

    recipient   = ForeignKey(User, related_name="notifications")
    type        = CharField(choices=Type.choices, default=Type.GENERAL)
    title       = CharField(max_length=200)
    body        = TextField()
    is_read     = BooleanField(default=False)
    job         = ForeignKey(Job, null=True, blank=True, on_delete=SET_NULL)
    created_at  = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

#### Helper

```python
# notifications/services.py
def notify(recipient, type, title, body, job=None):
    """Create a single Notification record. Extend here to add push/email."""
    return Notification.objects.create(
        recipient=recipient, type=type,
        title=title, body=body, job=job,
    )

def notify_many(recipients, type, title, body, job=None):
    """Bulk create notifications for a list of users."""
    Notification.objects.bulk_create([
        Notification(recipient=r, type=type, title=title, body=body, job=job)
        for r in recipients
    ])
```

#### Endpoints

| Method | URL | Permission | Purpose |
|---|---|---|---|
| GET | `/api/v1/notifications/` | Auth (own) | List own notifications, newest first |
| PATCH | `/api/v1/notifications/<id>/read/` | Auth | Mark one as read |
| POST | `/api/v1/notifications/mark-all-read/` | Auth | Mark all as read |
| GET | `/api/v1/notifications/unread-count/` | Auth | `{"count": N}` for badge |

---

### 7.8 attendance (NEW app)

#### Model

```python
class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        ABSENT    = "absent",    "Absent"

    job        = ForeignKey(Job, related_name="attendance_records")
    staff      = ForeignKey(User, related_name="attendance_records")
    status     = CharField(choices=Status.choices)
    confirmed_at = DateTimeField(auto_now_add=True)
    confirmed_by = ForeignKey(User, null=True, related_name="recorded_attendance")
    # GPS or PIN-based — store a simple confirmation token for now
    confirmation_token = CharField(max_length=64, blank=True)
    notes      = TextField(blank=True)

    class Meta:
        unique_together = [("job", "staff")]
```

#### Confirmation algorithm

The simplest reliable approach without GPS:
1. Admin generates a 6-digit PIN per job on the morning of the move.
2. Each staff member calls `POST /api/v1/attendance/confirm/` with their PIN.
3. The system matches the PIN to the job, verifies the staff is assigned, and marks them `confirmed`.

```python
# attendance/services.py
def confirm_attendance(job, staff, token):
    """
    Validates that `token` matches job.attendance_pin,
    staff is assigned to the job, and job is ASSIGNED or IN_PROGRESS.
    Creates AttendanceRecord(status=CONFIRMED).
    Raises AttendanceError on any violation.
    """

def mark_absent(job, staff_id, recorded_by):
    """
    Admin-only. Creates AttendanceRecord(status=ABSENT) for a staff member
    who did not confirm before the job starts.
    """
```

#### Endpoints

| Method | URL | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/attendance/confirm/` | Staff | Staff confirms presence with PIN |
| POST | `/api/v1/attendance/generate-pin/<job_id>/` | Admin | Generate morning PIN for job |
| GET | `/api/v1/attendance/<job_id>/` | Admin | Full attendance list for job |
| POST | `/api/v1/attendance/<job_id>/mark-absent/` | Admin | Mark a staff as absent |

---

### 7.9 reports

No model changes. Add new aggregations:

- `/api/v1/reports/attendance/` — attendance rate per job and per staff
- `/api/v1/reports/applications/` — application volume, approval rate

---

## 8. New Feature Implementation Guide

### 8.1 Job Application Flow

**Step 1 — Extend Job model** (`jobs/models.py`):

```python
application_deadline = models.DateTimeField(null=True, blank=True)
max_applicants       = models.PositiveSmallIntegerField(default=20)
```

**Step 2 — Add JobApplication model** (`jobs/models.py`):

```python
class JobApplication(models.Model):
    # (full definition in Section 7.4)
```

**Step 3 — Write service** (`jobs/services.py`):

```python
@transaction.atomic
def apply_for_job(job: Job, staff: User) -> JobApplication:
    from django.utils import timezone

    if job.status != Job.Status.PENDING:
        raise ApplicationError("Applications are only open for PENDING jobs.")

    if job.application_deadline and timezone.now() > job.application_deadline:
        raise ApplicationError("The application deadline for this job has passed.")

    current_count = job.applications.filter(
        status=JobApplication.Status.APPLIED
    ).count()
    if current_count >= job.max_applicants:
        raise ApplicationError("This job has reached its maximum number of applicants.")

    if job.applications.filter(staff=staff).exists():
        raise ApplicationError("You have already applied for this job.")

    return JobApplication.objects.create(job=job, staff=staff)
```

**Step 4 — Views & URLs** (`jobs/views.py`, `jobs/urls.py`):

```python
class ApplyForJobView(APIView):
    permission_classes = [IsAuthenticated, IsMoverStaff]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        try:
            application = apply_for_job(job=job, staff=request.user)
        except ApplicationError as e:
            return Response({"error": str(e)}, status=400)
        return Response(JobApplicationSerializer(application).data, status=201)

    def delete(self, request, pk):
        application = get_object_or_404(
            JobApplication, job_id=pk, staff=request.user
        )
        if application.status != JobApplication.Status.APPLIED:
            return Response({"error": "Cannot withdraw a processed application."}, status=400)
        application.status = JobApplication.Status.WITHDRAWN
        application.save()
        return Response({"message": "Application withdrawn."})
```

---

### 8.2 Admin Approval & Supervisor Selection

**Service** (`jobs/services.py`):

```python
@transaction.atomic
def approve_applications(job, approved_staff_ids, supervisor_id, reviewed_by):
    """
    approved_staff_ids : list of User PKs to approve (must include supervisor_id)
    supervisor_id      : User PK of the chosen supervisor
    """
    if supervisor_id not in approved_staff_ids:
        raise ApplicationError("Supervisor must be in the approved staff list.")

    applications = JobApplication.objects.filter(
        job=job, staff_id__in=approved_staff_ids, status=JobApplication.Status.APPLIED
    )
    found_ids = set(applications.values_list("staff_id", flat=True))
    missing = set(approved_staff_ids) - found_ids
    if missing:
        raise ApplicationError(f"Staff IDs {sorted(missing)} have no APPLIED application.")

    # Approve selected
    for app in applications:
        app.status = JobApplication.Status.APPROVED
        app.reviewed_by = reviewed_by
        app.reviewed_at = timezone.now()
        app.save()

        role = JobAssignment.Role.SUPERVISOR if app.staff_id == supervisor_id \
               else JobAssignment.Role.MOVER
        JobAssignment.objects.create(
            job=job, staff=app.staff, role=role, assigned_by=reviewed_by
        )

    # Reject remaining APPLIED applications
    rejected_apps = job.applications.filter(status=JobApplication.Status.APPLIED)
    rejected_staff = list(rejected_apps.values_list("staff", flat=True))
    rejected_apps.update(
        status=JobApplication.Status.REJECTED,
        reviewed_by=reviewed_by,
        reviewed_at=timezone.now(),
    )

    # Lock approved staff availability
    StaffProfile.objects.filter(user_id__in=approved_staff_ids).update(is_available=False)

    # Transition job
    job.status = Job.Status.ASSIGNED
    job.save(update_fields=["status", "updated_at"])

    # Fire signal → notifications triggered in jobs/signals.py
    from jobs.signals import applications_approved
    applications_approved.send(
        sender=job.__class__,
        job=job,
        approved_staff_ids=list(approved_staff_ids),
        rejected_staff_ids=rejected_staff,
    )

    return job
```

**Signal** (`jobs/signals.py`):

```python
from django.dispatch import Signal, receiver
from notifications.services import notify, notify_many
from accounts.models import User

applications_approved = Signal()

@receiver(applications_approved)
def send_approval_notifications(sender, job, approved_staff_ids, rejected_staff_ids, **kwargs):
    approved_users = User.objects.filter(pk__in=approved_staff_ids)

    # Build team list body
    team_names = ", ".join(u.get_full_name() for u in approved_users)
    team_body = (
        f"You have been selected for '{job.title}' on {job.scheduled_date}.\n"
        f"Your team: {team_names}.\n"
        f"Please confirm your attendance on the morning of the move."
    )

    notify_many(
        recipients=approved_users,
        type="application_approved",
        title=f"You're in! — {job.title}",
        body=team_body,
        job=job,
    )

    rejected_users = User.objects.filter(pk__in=rejected_staff_ids)
    notify_many(
        recipients=rejected_users,
        type="application_rejected",
        title=f"Application Update — {job.title}",
        body=f"Thank you for applying for '{job.title}'. "
             f"Unfortunately you were not selected for this move.",
        job=job,
    )
```

---

### 8.3 Attendance / Presence Confirmation

Full service logic in Section 7.8. The PIN is stored on the Job record:

```python
# Add to Job model
attendance_pin = models.CharField(max_length=6, blank=True)
```

```python
# attendance/services.py
import random, string

def generate_attendance_pin(job):
    pin = "".join(random.choices(string.digits, k=6))
    job.attendance_pin = pin
    job.save(update_fields=["attendance_pin", "updated_at"])
    # Notify all assigned staff
    from notifications.services import notify_many
    staff_users = [a.staff for a in job.assignments.select_related("staff")]
    notify_many(
        recipients=staff_users,
        type="attendance_reminder",
        title=f"Attendance PIN — {job.title}",
        body=f"Your attendance PIN for today's move is: {pin}. "
             f"Use it at the site to confirm your presence.",
        job=job,
    )
    return pin
```

---

### 8.4 Payment Disbursement Simulation

```python
# billing/services.py
@transaction.atomic
def disburse_payment(invoice, disbursed_by):
    if invoice.payment_status != Invoice.PaymentStatus.PAID:
        raise BillingError("Invoice must be fully paid before disbursing.")

    existing = invoice.disbursements.filter(
        status=PaymentDisbursement.Status.DISBURSED
    ).exists()
    if existing:
        raise BillingError("Payment has already been disbursed for this invoice.")

    assignments = invoice.job.assignments.select_related("staff")
    count = assignments.count()
    if count == 0:
        raise BillingError("No staff assigned to this job.")

    per_staff_amount = (invoice.amount_paid / count).quantize(Decimal("0.01"))

    disbursements = []
    for assignment in assignments:
        ref = _generate_disbursement_ref(assignment.staff)
        disbursements.append(PaymentDisbursement(
            invoice=invoice,
            staff=assignment.staff,
            amount=per_staff_amount,
            status=PaymentDisbursement.Status.DISBURSED,
            disbursed_by=disbursed_by,
            disbursed_at=timezone.now(),
            transaction_ref=ref,
        ))
    PaymentDisbursement.objects.bulk_create(disbursements)

    # Notify each staff member
    from notifications.services import notify
    for d in disbursements:
        notify(
            recipient=d.staff,
            type="payment_disbursed",
            title="Payment Received",
            body=f"KES {d.amount} has been disbursed for '{invoice.job.title}'. "
                 f"Ref: {d.transaction_ref}",
            job=invoice.job,
        )

    return disbursements
```

---

### 8.5 Recommendation Engine (Review-Based)

The score is already computed in `StaffProfile.recalculate_scores()` via signal.

**Key rule:** Score is based **only on supervisor reviews**, not job count.

When staff apply for the next job, the application list endpoint returns
`recommendation_score` for each applicant so the admin can sort and compare:

```python
# In JobApplicationSerializer
recommendation_score = serializers.SerializerMethodField()

def get_recommendation_score(self, obj):
    profile = getattr(obj.staff, "staff_profile", None)
    return float(profile.recommendation_score) if profile else 1.0
```

The admin dashboard should present applicants sorted by score descending.
The service does not auto-approve — the **admin retains full approval authority**.

---

### 8.6 Notifications

See Section 7.7. Always call `notify()` or `notify_many()` from service or
signal functions — never directly from a view.

---

## 9. Swagger / OpenAPI Documentation

### Installation

```bash
pip install drf-spectacular
```

### settings.py additions

```python
INSTALLED_APPS += ["drf_spectacular"]

REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"

SPECTACULAR_SETTINGS = {
    "TITLE": "E-Movers API",
    "DESCRIPTION": (
        "Internal management API for the E-Movers moving company. "
        "Handles jobs, staff, billing, reviews, attendance, and notifications."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "Auth", "description": "JWT authentication"},
        {"name": "Users", "description": "User management"},
        {"name": "Customers", "description": "Customer CRUD"},
        {"name": "Fleet", "description": "Truck management"},
        {"name": "Jobs", "description": "Job lifecycle and applications"},
        {"name": "Billing", "description": "Invoices, payments, disbursements"},
        {"name": "Reviews", "description": "Supervisor reviews and scoring"},
        {"name": "Notifications", "description": "In-app notification system"},
        {"name": "Attendance", "description": "Attendance confirmation"},
        {"name": "Reports", "description": "Admin reporting and KPIs"},
    ],
}
```

### Root urls.py additions

```python
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),
]
```

Access Swagger UI at: `http://localhost:8000/api/docs/`

### Decorating views for Swagger

Every view or APIView must be tagged and documented:

```python
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

class ApplyForJobView(APIView):
    permission_classes = [IsAuthenticated, IsMoverStaff]

    @extend_schema(
        tags=["Jobs"],
        summary="Apply for a job",
        description=(
            "A mover-staff member applies for a pending job. "
            "Blocked if the deadline has passed or the max applicant cap is reached."
        ),
        request=None,
        responses={
            201: JobApplicationSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Success",
                value={"id": 1, "job": 5, "staff": 3, "status": "applied"},
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request, pk):
        ...

    @extend_schema(
        tags=["Jobs"],
        summary="Withdraw job application",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def delete(self, request, pk):
        ...
```

For `generics` views, use `@extend_schema` on the class:

```python
@extend_schema(tags=["Notifications"])
class NotificationListView(generics.ListAPIView):
    ...
```

### Documenting query parameters

```python
@extend_schema(
    parameters=[
        OpenApiParameter("days", OpenApiTypes.INT, description="Window in days (1–365, default 30)"),
        OpenApiParameter("available_only", OpenApiTypes.BOOL, description="Filter to available staff only"),
    ]
)
```

### Generate schema file (for CI or frontend codegen)

```bash
python manage.py spectacular --color --file schema.yml
```

---

## 10. Serializer Patterns

### Rule: one serializer per use-case, not per model

| Suffix | When to use |
|---|---|
| `ListSerializer` | Lightweight fields for list views |
| `Serializer` (detail) | Full nested response |
| `CreateSerializer` | POST body — writable fields only |
| `UpdateSerializer` | PATCH body — editable fields only |
| `<Action>Serializer` | Non-CRUD actions (e.g. `ApproveApplicationsSerializer`) |

### Action serializer example

```python
class ApproveApplicationsSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/approve-applications/"""
    approved_staff_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1
    )
    supervisor_id = serializers.IntegerField()

    def validate(self, data):
        if data["supervisor_id"] not in data["approved_staff_ids"]:
            raise serializers.ValidationError(
                "supervisor_id must be in approved_staff_ids."
            )
        return data
```

### Always use `read_only_fields`

```python
class Meta:
    model = MyModel
    fields = [...]
    read_only_fields = ["id", "created_at", "updated_at", "created_by"]
```

### Display fields pattern

```python
status_display = serializers.CharField(source="get_status_display", read_only=True)
```

---

## 11. Permission Matrix

| Endpoint category | Admin | Staff | Public |
|---|---|---|---|
| Auth (login, refresh) | ✓ | ✓ | ✓ |
| Auth (register) | ✓ | ✗ | ✗ |
| Users (list, detail, delete) | ✓ | ✗ | ✗ |
| Customers (read) | ✓ | ✓ | ✗ |
| Customers (write/delete) | ✓ | ✗ | ✗ |
| Fleet (read) | ✓ | ✓ | ✗ |
| Fleet (write/delete) | ✓ | ✗ | ✗ |
| Jobs (read) | ✓ | ✓ | ✗ |
| Jobs (create/update/delete) | ✓ | ✗ | ✗ |
| Jobs — apply / withdraw | ✗ | ✓ | ✗ |
| Jobs — view applicants | ✓ | ✗ | ✗ |
| Jobs — approve applications | ✓ | ✗ | ✗ |
| Jobs — status transition | ✓ | ✓ (own jobs) | ✗ |
| Attendance — confirm | ✗ | ✓ | ✗ |
| Attendance — generate PIN / mark absent | ✓ | ✗ | ✗ |
| Billing — generate invoice / pay | ✓ | ✗ | ✗ |
| Billing — view invoices | ✓ | ✓ | ✗ |
| Billing — disburse | ✓ | ✗ | ✗ |
| Reviews — submit | ✗ | ✓ (supervisor) | ✗ |
| Reviews — view all | ✓ | ✗ | ✗ |
| Reviews — my-reviews | ✗ | ✓ | ✗ |
| Notifications — own | ✓ | ✓ | ✗ |
| Reports — all | ✓ | ✗ | ✗ |

---

## 12. Service Layer Rules

1. **Every write operation is a service function.** No business logic in views.
2. **Wrap in `@transaction.atomic`** any service that touches multiple tables.
3. **Raise a custom `*Error` exception** (never `Http404`, `PermissionDenied`, or DRF exceptions) from services. Views catch these and map to HTTP status codes.
4. **Custom exceptions live in the same `services.py` file** as the service they protect.
5. **Services return model instances**, never serialized data.
6. **Never call `notify()` from a view.** Notifications fire from services or signals.

### Custom exception example

```python
class ApplicationError(Exception):
    pass

class AttendanceError(Exception):
    pass
```

### View error mapping

```python
try:
    result = my_service(...)
except MyError as e:
    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

---

## 13. Signal Conventions

- Register all signals in `<app>/signals.py`.
- Import signals in `<app>/apps.py::ready()`:

```python
def ready(self):
    import myapp.signals  # noqa: F401
```

- Custom signals (not `post_save`) live in the app that **sends** them.
- Receiver logic that touches **another app's models** lives in the **sending app's** signals.py, not the receiving app.

---

## 14. Error Response Contract

All error responses follow this shape:

```json
{
  "error": "Human-readable description of what went wrong."
}
```

Validation errors from DRF serializers follow the default DRF shape:

```json
{
  "field_name": ["Error message."]
}
```

Do not mix these formats. Views that call services use `{"error": ...}`;
views that call `serializer.is_valid(raise_exception=True)` produce DRF's format automatically.

---

## 15. Testing Guide

### Test types

| Type | File | Tool |
|---|---|---|
| Unit (service logic) | `<app>/tests/test_services.py` | `pytest-django` + `factory-boy` |
| Integration (full flow) | `integration_tests.py` | Django test `Client` |
| Swagger schema validity | CI step | `drf-spectacular` schema check |

### Running tests

```bash
# Integration suite (existing)
python integration_tests.py

# Unit tests (after adding pytest.ini)
pytest

# Schema validation
python manage.py spectacular --validate --fail-on-warn
```

### `pytest.ini`

```ini
[pytest]
DJANGO_SETTINGS_MODULE = e_movers.settings
python_files = tests/test_*.py
python_classes = Test*
python_functions = test_*
```

### Factory example

```python
# jobs/tests/factories.py
import factory
from factory.django import DjangoModelFactory
from accounts.models import User
from jobs.models import Job

class StaffUserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"staff{n}@test.com")
    first_name = "Test"
    last_name = factory.Sequence(lambda n: f"Staff{n}")
    role = User.Role.STAFF
    is_active = True
    password = factory.PostGenerationMethodCall("set_password", "Test1234!")

class JobFactory(DjangoModelFactory):
    class Meta:
        model = Job

    title = factory.Sequence(lambda n: f"Test Move {n}")
    status = Job.Status.PENDING
    move_size = Job.MoveSizeCategory.ONE_BED
    scheduled_date = "2025-12-01"
    estimated_distance_km = "10.00"
    pickup_address = "A"
    dropoff_address = "B"
```

### Service unit test example

```python
# jobs/tests/test_services.py
import pytest
from jobs.services import apply_for_job, ApplicationError
from jobs.tests.factories import StaffUserFactory, JobFactory

@pytest.mark.django_db
class TestApplyForJob:
    def test_successful_application(self):
        job = JobFactory()
        staff = StaffUserFactory()
        app = apply_for_job(job=job, staff=staff)
        assert app.status == "applied"
        assert app.staff == staff

    def test_duplicate_application_raises(self):
        job = JobFactory()
        staff = StaffUserFactory()
        apply_for_job(job=job, staff=staff)
        with pytest.raises(ApplicationError, match="already applied"):
            apply_for_job(job=job, staff=staff)

    def test_deadline_passed_raises(self):
        from django.utils import timezone
        from datetime import timedelta
        job = JobFactory(application_deadline=timezone.now() - timedelta(hours=1))
        staff = StaffUserFactory()
        with pytest.raises(ApplicationError, match="deadline"):
            apply_for_job(job=job, staff=staff)
```

### Integration test additions (extend `integration_tests.py`)

Add test blocks for:
- `test_job_apply` — staff applies, gets 201
- `test_job_apply_deadline_passed` — gets 400
- `test_job_approve_applications` — admin approves, notification exists
- `test_attendance_confirm` — staff confirms with PIN, gets 201
- `test_disbursement` — admin disburses, all records created
- `test_notification_list` — staff sees their notifications
- `test_notification_mark_read` — unread count decrements

---

## 16. Database Schema Notes

### Key relationships

```
User (1) ──── (1) StaffProfile
User (1) ──── (N) JobApplication
User (1) ──── (N) JobAssignment
User (1) ──── (N) Notification
User (1) ──── (N) AttendanceRecord

Job (1) ──── (N) JobApplication
Job (1) ──── (N) JobAssignment
Job (1) ──── (N) JobTruck
Job (1) ──── (1) Invoice
Job (1) ──── (N) StaffReview
Job (1) ──── (N) AttendanceRecord

Invoice (1) ──── (N) Payment
Invoice (1) ──── (N) PaymentDisbursement
```

### Index recommendations (production)

```python
# Add to Meta classes where filtering is common
class Meta:
    indexes = [
        models.Index(fields=["status"]),           # Job, JobApplication
        models.Index(fields=["is_read"]),           # Notification
        models.Index(fields=["payment_status"]),    # Invoice
        models.Index(fields=["scheduled_date"]),    # Job
    ]
```

---

## 17. Seed Data

The `seed_data` management command must be updated to include:

```python
# New seed additions in management/commands/seed_data.py

# For each of the first 3 jobs (pending):
# - Create JobApplication for 8 staff each
# - Leave 2 jobs without applications (for unassigned tests)

# For completed jobs:
# - Create AttendanceRecord(status=confirmed) for all staff
# - Create PaymentDisbursement records

# Create 3 Notifications per staff user
```

---

## 18. Deployment Checklist

```
□ DEBUG = False
□ SECRET_KEY from environment variable (not hardcoded)
□ ALLOWED_HOSTS set to domain
□ DATABASES switched to PostgreSQL
□ CORS_ALLOW_ALL_ORIGINS = False; CORS_ALLOWED_ORIGINS set
□ STATIC_ROOT set; collectstatic run
□ Gunicorn + nginx configured
□ HTTPS enforced (SECURE_SSL_REDIRECT = True)
□ SESSION_COOKIE_SECURE = True
□ CSRF_COOKIE_SECURE = True
□ Run: python manage.py spectacular --validate (schema passes)
□ Run: python integration_tests.py (all pass)
□ Swagger docs URL secured or disabled in production
```

---

## 19. Changelog & What Is New

### v1.0 (current codebase)
- accounts, customers, fleet, jobs (auto-allocate), billing, reviews, reports
- JWT auth, role-based permissions
- Integration test suite (67 tests)

### v1.1 (this SKILL.md target)

| Feature | App affected | Status |
|---|---|---|
| Job application model + apply/withdraw endpoints | jobs | NEW |
| Admin approval + supervisor selection | jobs | NEW |
| Application-based notifications (approved/rejected + team list) | jobs, notifications | NEW |
| Attendance PIN generation | attendance | NEW |
| Staff attendance confirmation endpoint | attendance | NEW |
| Payment disbursement simulation | billing | NEW |
| Disbursement notifications | billing, notifications | NEW |
| Notification list + mark-read endpoints | notifications | NEW |
| Swagger/OpenAPI with drf-spectacular | all apps | NEW |
| `@extend_schema` decorators on all views | all apps | NEW |
| `pytest-django` + factory-boy unit test scaffold | all apps | NEW |
| Reports: attendance rate, application volume | reports | NEW |

---

*End of SKILL.md — keep this document updated as the project evolves.*