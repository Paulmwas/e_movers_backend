# E-Movers Backend API

> **Django REST Framework** backend for the E-Movers moving company management system.
> Internal operational tool for admins and mover staff — not a customer-facing booking platform.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Quick Start](#4-quick-start)
5. [Authentication](#5-authentication)
6. [Role-Based Access](#6-role-based-access)
7. [Business Flow — End-to-End](#7-business-flow--end-to-end)
8. [API Reference](#8-api-reference)
   - 8.1 [Auth](#81-auth)
   - 8.2 [Users](#82-users)
   - 8.3 [Customers](#83-customers)
   - 8.4 [Fleet (Trucks)](#84-fleet-trucks)
   - 8.5 [Jobs](#85-jobs)
   - 8.6 [Job Application Flow](#86-job-application-flow)
   - 8.7 [Attendance](#87-attendance)
   - 8.8 [Billing — Invoices & Payments](#88-billing--invoices--payments)
   - 8.9 [Payment Disbursement](#89-payment-disbursement)
   - 8.10 [Reviews](#810-reviews)
   - 8.11 [Notifications](#811-notifications)
   - 8.12 [Reports](#812-reports)
9. [Error Response Format](#9-error-response-format)
10. [Recommendation Score Algorithm](#10-recommendation-score-algorithm)
11. [Running Tests](#11-running-tests)
12. [Database Reset & Re-seed](#12-database-reset--re-seed)
13. [Deployment Notes](#13-deployment-notes)

---

## 1. Overview

E-Movers manages the full lifecycle of a moving job:

| Phase | Who | What happens |
|---|---|---|
| Job creation | Admin | Creates a job with location, schedule, and move size |
| Application | Staff | Browse pending jobs and apply; admin caps and deadlines enforced |
| Approval | Admin | Reviews applicants, approves a subset, designates supervisor |
| Notification | System | Approved staff get team list; rejected staff get a notice |
| Attendance | Admin + Staff | Admin generates a morning PIN; staff confirm presence with it |
| Execution | Supervisor | Starts job → completes job |
| Billing | Admin | Generates invoice → records simulated payment |
| Disbursement | Admin | Splits collected amount equally among all assigned staff |
| Review | Supervisor | Rates each mover across multiple categories |
| Next cycle | System | Recommendation scores update instantly; best-rated staff surface first in auto-allocation |

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 + Django REST Framework 3.15 |
| Auth | JWT — `djangorestframework-simplejwt` 5.3 |
| Filtering | `django-filter` 23.5 |
| CORS | `django-cors-headers` 4.3 |
| Database | SQLite (dev) / PostgreSQL (production) |

**Install all dependencies:**
```bash
pip install -r requirements.txt
```

---

## 3. Project Structure

```
e_movers_backend/
├── e_movers/               # Django project config
│   ├── settings.py         # All configuration
│   ├── urls.py             # Root URL router — prefix api/v1/
│   ├── asgi.py
│   └── wsgi.py
│
├── accounts/               # Custom user model, JWT auth, StaffProfile
├── customers/              # Customer CRUD
├── fleet/                  # Truck registry and status tracking
├── jobs/                   # Core job lifecycle + application flow
├── billing/                # Invoices, simulated payments, disbursements
├── reviews/                # Post-job supervisor reviews + score engine
├── notifications/          # In-app notification inbox
├── attendance/             # Morning PIN confirmation system
├── reports/                # Admin-only aggregated reporting (no DB models)
│
├── integration_tests.py    # 110-test end-to-end suite (run directly)
├── requirements.txt
├── manage.py
└── README.md
```

### App dependency graph

```
accounts
  ↑
customers  fleet
  ↑          ↑
  └── jobs ──┘
        ↑
   billing   reviews   notifications   attendance
        ↑
     reports (read-only queries across all apps)
```

No circular imports. Cross-app imports flow strictly downward.

---

## 4. Quick Start

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

### Windows

```powershell
git clone <repo>
cd e_movers_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

API base URL: **`http://localhost:8000/api/v1/`**

### Seed data credentials

| Account | Email | Password | Role |
|---|---|---|---|
| System admin | `admin@emovers.co.ke` | `Admin1234!` | `mover-admin` |
| Staff 01–15 | `staff01@emovers.co.ke` … `staff15@emovers.co.ke` | `Staff1234!` | `mover-staff` |

The seed command also creates 10 customers, 6 trucks, 8 jobs in various lifecycle stages, invoices, payments, and reviews.

**Re-seed (wipe and rebuild):**
```bash
python manage.py seed_data --flush
```

---

## 5. Authentication

All endpoints except `POST /api/v1/auth/login/` and `POST /api/v1/auth/token/refresh/` require:

```
Authorization: Bearer <access_token>
```

**Token lifetimes:**
- Access token: 60 minutes
- Refresh token: 7 days (auto-rotated on use; old refresh is blacklisted)

### Login

```
POST /api/v1/auth/login/
```

**Request body:**
```json
{
  "email": "admin@emovers.co.ke",
  "password": "Admin1234!"
}
```

**Response `200`:**
```json
{
  "message": "Login successful.",
  "user": {
    "id": 1,
    "email": "admin@emovers.co.ke",
    "first_name": "System",
    "last_name": "Admin",
    "role": "mover-admin",
    "phone": "+254700000001",
    "is_active": true,
    "date_joined": "2025-01-01T00:00:00Z"
  },
  "tokens": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>"
  }
}
```

**Error responses:**
- `401` — wrong password
- `403` — account deactivated

---

## 6. Role-Based Access

| Role | Value | Key capabilities |
|---|---|---|
| Mover Admin | `mover-admin` | Full access: create jobs, approve applicants, generate invoices, disburse payments, view all reports |
| Mover Staff | `mover-staff` | Apply for jobs, confirm attendance, start/complete assigned jobs, submit reviews (supervisor), view own notifications and reviews |

**Rule of thumb:** Any endpoint documented as "Admin" returns `403 Forbidden` when called by staff.

---

## 7. Business Flow — End-to-End

```
1.  Admin creates Job                POST /api/v1/jobs/
      └─ status = "pending"
      └─ application_deadline and max_applicants set (optional)

2.  Staff browse and apply           POST /api/v1/jobs/<id>/apply/
      └─ Deadline + max-applicant cap enforced automatically
      └─ Staff can withdraw          DELETE /api/v1/jobs/<id>/apply/

3.  Admin reviews applicants         GET  /api/v1/jobs/<id>/applications/
      └─ Listed by recommendation_score DESC (best candidates first)

4.  Admin approves + picks supervisor  POST /api/v1/jobs/<id>/approve-applications/
      └─ JobAssignments created for approved staff
      └─ Remaining APPLIED applications auto-rejected
      └─ Approved staff locked: is_available = False
      └─ Job status → "assigned"
      └─ [SIGNAL] Approved staff notified with full team list
      └─ [SIGNAL] Rejected staff notified politely

5.  Morning of move — Admin generates PIN   POST /api/v1/attendance/generate-pin/<id>/
      └─ 6-digit PIN stored on the job

6.  Each staff member confirms              POST /api/v1/attendance/confirm/
      └─ Submits PIN → AttendanceRecord(status=confirmed) created
      └─ Admin can mark no-shows absent     POST /api/v1/attendance/<id>/mark-absent/

7.  Supervisor starts job            POST /api/v1/jobs/<id>/status/  {"action": "start"}
      └─ Job status → "in_progress"

8.  Admin generates invoice          POST /api/v1/billing/invoices/generate/
      └─ Costs calculated: base + distance + staff + truck + 16% VAT

9.  Supervisor completes job         POST /api/v1/jobs/<id>/status/  {"action": "complete"}
      └─ Job status → "completed"
      └─ All staff released: is_available = True
      └─ All trucks released: status = "available"

10. Admin records payment            POST /api/v1/billing/invoices/<id>/pay/
      └─ Simulated payment (cash / M-Pesa / bank / card)
      └─ Partial payments supported; invoice tracks balance_due

11. Admin disburses to staff         POST /api/v1/billing/invoices/<id>/disburse/
      └─ Invoice must be fully PAID first
      └─ amount_paid split equally among all assigned staff
      └─ One PaymentDisbursement record per staff member
      └─ [NOTIFICATION] Each staff member notified of their payment

12. Supervisor reviews movers        POST /api/v1/reviews/bulk-create/
      └─ Ratings per (job, reviewee, category)
      └─ [SIGNAL] recommendation_score recalculated immediately per mover

13. Next job cycle
      └─ auto_allocate_job selects staff by recommendation_score DESC
      └─ Best-reviewed staff automatically surface first
```

---

## 8. API Reference

### 8.1 Auth

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/login/` | Public | Email + password → JWT tokens |
| `POST` | `/api/v1/auth/logout/` | Auth | Blacklist refresh token |
| `POST` | `/api/v1/auth/token/refresh/` | Public | Rotate access token using refresh |
| `GET` / `PATCH` | `/api/v1/auth/me/` | Auth | View or update own profile (`first_name`, `last_name`, `phone`) |
| `POST` | `/api/v1/auth/change-password/` | Auth | Change own password |
| `POST` | `/api/v1/auth/register/` | Admin | Create a new user account |

#### Register a new user

```
POST /api/v1/auth/register/
```

```json
{
  "email": "newstaff@emovers.co.ke",
  "password": "SecurePass1!",
  "first_name": "Jane",
  "last_name": "Doe",
  "role": "mover-staff",
  "phone": "+254712345678"
}
```

Role values: `mover-admin`, `mover-staff`

---

### 8.2 Users

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/` | Admin | List all users |
| `GET` | `/api/v1/users/available-staff/` | Admin | Available staff ordered by `recommendation_score DESC` |
| `GET` / `PATCH` / `DELETE` | `/api/v1/users/<id>/` | Admin | User detail; `DELETE` = soft-delete (`is_active=false`) |
| `GET` / `PATCH` | `/api/v1/users/<id>/staff-profile/` | Admin | View or update availability and notes |

#### Query parameters for `GET /api/v1/users/`

| Param | Values | Example |
|---|---|---|
| `role` | `mover-admin` \| `mover-staff` | `?role=mover-staff` |
| `is_active` | `true` \| `false` | `?is_active=true` |
| `search` | name, email, phone | `?search=jane` |
| `ordering` | `date_joined`, `first_name`, `last_name` | `?ordering=-date_joined` |

#### Staff profile fields (PATCH)

```json
{
  "is_available": true,
  "notes": "Experienced with piano moves."
}
```

> `average_rating` and `recommendation_score` are read-only — they are recalculated automatically by the review signal.

---

### 8.3 Customers

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/customers/` | Admin + Staff | List customers |
| `POST` | `/api/v1/customers/` | Admin | Create customer |
| `GET` / `PATCH` / `DELETE` | `/api/v1/customers/<id>/` | Admin + Staff | Customer detail; `DELETE` blocked if active jobs exist |

#### Create a customer

```
POST /api/v1/customers/
```

```json
{
  "first_name": "Alice",
  "last_name": "Kamau",
  "email": "alice@example.com",
  "phone": "+254722000001",
  "address": "Karen, Nairobi"
}
```

#### Query parameters for `GET /api/v1/customers/`

| Param | Description |
|---|---|
| `search` | Name, email, or phone |
| `ordering` | `first_name`, `last_name`, `created_at` |

---

### 8.4 Fleet (Trucks)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/fleet/` | Admin + Staff | List all trucks |
| `POST` | `/api/v1/fleet/` | Admin | Register a truck |
| `GET` | `/api/v1/fleet/available/` | Admin + Staff | Only trucks with `status=available`, ordered by `capacity_tons DESC` |
| `GET` / `PATCH` / `DELETE` | `/api/v1/fleet/<id>/` | Admin | Truck detail; `DELETE` blocked if `status=on_job` |

#### Create a truck

```
POST /api/v1/fleet/
```

```json
{
  "plate_number": "KDB 001A",
  "make": "Isuzu",
  "model": "NPR",
  "year": 2022,
  "truck_type": "medium",
  "capacity_tons": "3.50",
  "next_service_date": "2026-06-01"
}
```

#### Truck status values

| Value | Meaning |
|---|---|
| `available` | Ready to be assigned |
| `on_job` | Currently assigned to an active job |
| `maintenance` | Out of service |

#### Truck type values

`small` · `medium` · `large` · `extra_large`

#### Query parameters for `GET /api/v1/fleet/`

| Param | Example |
|---|---|
| `status` | `?status=available` |
| `truck_type` | `?truck_type=large` |
| `search` | `?search=KDB` |

---

### 8.5 Jobs

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/jobs/` | Admin + Staff | List jobs |
| `POST` | `/api/v1/jobs/` | Admin | Create job |
| `GET` | `/api/v1/jobs/unassigned/` | Admin + Staff | PENDING jobs with no staff or truck assignments |
| `GET` / `PATCH` / `DELETE` | `/api/v1/jobs/<id>/` | Admin | Job detail; `DELETE` blocked if `in_progress` or `completed` |
| `POST` | `/api/v1/jobs/<id>/auto-allocate/` | Admin | Auto-assign staff + trucks by score |
| `POST` | `/api/v1/jobs/<id>/assign-staff/` | Admin | Manually assign specific staff |
| `POST` | `/api/v1/jobs/<id>/assign-trucks/` | Admin | Manually assign specific trucks |
| `POST` | `/api/v1/jobs/<id>/status/` | Admin + Staff | Transition job through status machine |

#### Create a job

```
POST /api/v1/jobs/
```

```json
{
  "title": "3-Bedroom Move — Westlands to Karen",
  "customer": 4,
  "move_size": "three_bedroom",
  "pickup_address": "12 Westlands Rd, Nairobi",
  "dropoff_address": "5 Karen Blvd, Nairobi",
  "estimated_distance_km": "18.50",
  "scheduled_date": "2026-05-20",
  "scheduled_time": "07:00:00",
  "requested_staff_count": 8,
  "requested_truck_count": 2,
  "application_deadline": "2026-05-18T18:00:00+03:00",
  "max_applicants": 20,
  "notes": "Customer has fragile art pieces.",
  "special_instructions": "Wrap piano in moving blankets."
}
```

**`application_deadline`** and **`max_applicants`** are optional. When omitted, applications are open until the admin manually approves them.

#### Move size values

`studio` · `one_bedroom` · `two_bedroom` · `three_bedroom` · `office_small` · `office_large`

#### Job status machine

```
pending ──────────────► assigned ──► in_progress ──► completed
   │                        │               │
   └──────────────────────► cancelled ◄─────┘
```

Terminal states (`completed`, `cancelled`) cannot be transitioned further.

#### Job status transition

```
POST /api/v1/jobs/<id>/status/
```

```json
{ "action": "start" }
```

| Action | From | To | Who |
|---|---|---|---|
| `start` | `assigned` | `in_progress` | Admin or assigned supervisor |
| `complete` | `in_progress` | `completed` | Admin or assigned supervisor |
| `cancel` | `pending` / `assigned` / `in_progress` | `cancelled` | Admin only |

On `complete` or `cancel`: all assigned staff are released (`is_available=true`) and all trucks are released (`status=available`).

#### Auto-allocate

```
POST /api/v1/jobs/<id>/auto-allocate/
```

```json
{
  "num_movers": 8,
  "num_trucks": 2
}
```

Defaults: `num_movers=10`, `num_trucks=1`.

Selects active, available staff ordered by `recommendation_score DESC`. The top candidate becomes supervisor; the rest become movers. Safe to call multiple times — re-running releases the previous assignment first.

#### Manual staff assignment

```
POST /api/v1/jobs/<id>/assign-staff/
```

```json
{ "staff_ids": [3, 7, 12, 15] }
```

#### Manual truck assignment

```
POST /api/v1/jobs/<id>/assign-trucks/
```

```json
{ "truck_ids": [2, 5] }
```

#### Query parameters for `GET /api/v1/jobs/`

| Param | Values / Example |
|---|---|
| `status` | `pending` \| `assigned` \| `in_progress` \| `completed` \| `cancelled` |
| `move_size` | `studio` \| `one_bedroom` \| … |
| `customer` | `?customer=4` |
| `scheduled_date_after` | `?scheduled_date_after=2026-01-01` |
| `scheduled_date_before` | `?scheduled_date_before=2026-12-31` |
| `has_supervisor` | `?has_supervisor=true` |
| `is_unassigned` | `?is_unassigned=true` |
| `search` | job title, customer name, address |
| `ordering` | `scheduled_date`, `created_at`, `status` |

---

### 8.6 Job Application Flow

Staff apply for pending jobs. The admin reviews all applicants ranked by performance and approves a subset, designating one as supervisor.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/jobs/<id>/apply/` | Staff | Apply for a pending job |
| `DELETE` | `/api/v1/jobs/<id>/apply/` | Staff | Withdraw an active (APPLIED) application |
| `GET` | `/api/v1/jobs/<id>/applications/` | Admin | List all applicants for a job, ranked by score |
| `POST` | `/api/v1/jobs/<id>/approve-applications/` | Admin | Approve subset, designate supervisor, reject the rest |
| `GET` | `/api/v1/jobs/my-applications/` | Staff | Own application history |

#### Apply for a job

```
POST /api/v1/jobs/7/apply/
```

No request body. The authenticated staff member is the applicant.

**Response `201`:**
```json
{
  "message": "Application submitted successfully.",
  "application": {
    "id": 42,
    "job": 7,
    "job_title": "3-Bedroom Move — Westlands to Karen",
    "job_scheduled_date": "2026-05-20",
    "staff": 5,
    "staff_name": "John Mwangi",
    "recommendation_score": 0.84,
    "average_rating": 4.0,
    "status": "applied",
    "applied_at": "2026-05-10T09:15:00Z"
  }
}
```

**Business rules enforced:**
- Job must be `pending`
- Deadline must not have passed (if set)
- `max_applicants` cap must not be reached
- Staff must not already have an active application for this job
- Staff account must be active

#### Withdraw an application

```
DELETE /api/v1/jobs/7/apply/
```

Only possible while `status=applied`. Returns `400` if already approved/rejected.

#### List applicants (Admin)

```
GET /api/v1/jobs/7/applications/
```

Results are ordered by `recommendation_score DESC` so the best candidates appear at the top. Supports `?status=applied|approved|rejected|withdrawn` filter.

**Response `200` (paginated):**
```json
{
  "count": 12,
  "results": [
    {
      "id": 42,
      "staff": 5,
      "staff_name": "John Mwangi",
      "staff_email": "staff05@emovers.co.ke",
      "recommendation_score": 0.84,
      "average_rating": 4.0,
      "status": "applied",
      "applied_at": "2026-05-10T09:15:00Z"
    }
  ]
}
```

#### Approve applications (Admin)

```
POST /api/v1/jobs/7/approve-applications/
```

```json
{
  "approved_staff_ids": [5, 8, 11, 13, 14, 15, 16, 17],
  "supervisor_id": 5
}
```

**What happens on approval:**
1. Selected staff applications → `approved`
2. `JobAssignment` records created (supervisor + movers)
3. All remaining `applied` applications → `rejected`
4. Approved staff locked: `is_available = false`
5. Job status → `assigned`
6. Approved staff receive notification with team list
7. Rejected staff receive a polite rejection notification

**Response `200`:**
```json
{
  "message": "Applications approved. Job is now ASSIGNED.",
  "job": { ... }
}
```

**Error cases:**
- `400` if `supervisor_id` is not in `approved_staff_ids`
- `400` if any staff ID has no `applied` application for this job
- `400` if job is not `pending`

#### Own application history (Staff)

```
GET /api/v1/jobs/my-applications/
```

Supports `?status=applied|approved|rejected|withdrawn`.

#### Application status values

| Value | Meaning |
|---|---|
| `applied` | Submitted, awaiting admin review |
| `approved` | Admin selected this staff member |
| `rejected` | Admin did not select this staff member |
| `withdrawn` | Staff withdrew before admin reviewed |

---

### 8.7 Attendance

PIN-based confirmation system. On the morning of each move, the admin generates a 6-digit PIN and shares it with the team. Staff submit the PIN to confirm their presence.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/attendance/generate-pin/<job_id>/` | Admin | Generate the morning attendance PIN for a job |
| `POST` | `/api/v1/attendance/confirm/` | Staff | Confirm attendance by submitting PIN |
| `GET` | `/api/v1/attendance/<job_id>/` | Admin + Staff | Full attendance list for a job |
| `POST` | `/api/v1/attendance/<job_id>/mark-absent/` | Admin | Manually mark a staff member as absent |

#### Generate PIN (morning of move)

```
POST /api/v1/attendance/generate-pin/7/
```

No request body required.

**Response `200`:**
```json
{
  "message": "PIN generated for '3-Bedroom Move — Westlands to Karen'. Share it with your team.",
  "job_id": 7,
  "pin": "483921"
}
```

The PIN is stored on the job. Calling this endpoint again overwrites the previous PIN. Job must be `assigned` or `in_progress`.

#### Staff confirms attendance

```
POST /api/v1/attendance/confirm/
```

```json
{
  "job_id": 7,
  "pin": "483921"
}
```

**Response `201`:**
```json
{
  "message": "Attendance confirmed. See you on the move!",
  "record": {
    "id": 18,
    "job": 7,
    "job_title": "3-Bedroom Move — Westlands to Karen",
    "staff": 5,
    "staff_name": "John Mwangi",
    "status": "confirmed",
    "confirmed_at": "2026-05-20T06:47:00Z"
  }
}
```

**Error cases:**
- `400` — wrong PIN
- `400` — staff is not assigned to this job
- `400` — attendance already recorded

#### View attendance for a job

```
GET /api/v1/attendance/7/
```

Returns all attendance records (confirmed + absent) for the job.

#### Mark a staff member absent

```
POST /api/v1/attendance/7/mark-absent/
```

```json
{
  "staff_id": 12,
  "notes": "Did not respond to calls."
}
```

Only possible if no attendance record exists yet for that staff member.

#### Attendance status values

| Value | Meaning |
|---|---|
| `confirmed` | Staff submitted the correct PIN |
| `absent` | Marked absent by admin |

---

### 8.8 Billing — Invoices & Payments

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/billing/invoices/` | Admin + Staff | List all invoices |
| `POST` | `/api/v1/billing/invoices/generate/` | Admin | Calculate costs and create or refresh an invoice |
| `GET` / `PATCH` | `/api/v1/billing/invoices/<id>/` | Admin + Staff | Invoice detail with full payment history |
| `POST` | `/api/v1/billing/invoices/<id>/pay/` | Admin | Record a simulated payment |
| `GET` | `/api/v1/billing/payments/` | Admin + Staff | Full payment history |

#### Cost formula (all amounts in KES)

```
Base charge      =  2,000
Distance charge  =    100  ×  estimated_distance_km
Staff charge     =    500  ×  assigned_staff_count
Truck charge     =  1,500  ×  assigned_truck_count
────────────────────────────────────────────────────
Subtotal         =  sum of above
VAT (16%)        =  subtotal × 0.16
────────────────────────────────────────────────────
Total            =  subtotal + VAT
```

The formula runs fresh every time `generate/` is called. If assignments change before the job starts, call `generate/` again to get the updated amount.

#### Generate an invoice

```
POST /api/v1/billing/invoices/generate/
```

```json
{
  "job_id": 7,
  "due_date": "2026-06-01",
  "notes": "Payment via M-Pesa preferred."
}
```

`due_date` and `notes` are optional. If an invoice already exists for the job and it is not fully paid, it is updated in place. Raises `400` if the invoice is already `paid`.

#### Record a simulated payment

```
POST /api/v1/billing/invoices/5/pay/
```

```json
{
  "amount": 15000.00,
  "method": "mpesa",
  "notes": "Customer confirmed ref: MPESA123"
}
```

Payment method values: `cash` · `mpesa` · `bank_transfer` · `card`

Partial payments are supported. Call this endpoint multiple times until `balance_due` reaches `0` and `payment_status` becomes `paid`. Each payment generates a simulated reference: `SIM-MPE-<timestamp>-<hex>`.

#### Invoice payment status values

| Value | Meaning |
|---|---|
| `unpaid` | No payments recorded yet |
| `partial` | Some payments received; balance remaining |
| `paid` | Fully paid — disbursement is now unlocked |
| `waived` | Admin waived the remaining balance |

#### Query parameters for `GET /api/v1/billing/invoices/`

| Param | Example |
|---|---|
| `payment_status` | `?payment_status=unpaid` |
| `job` | `?job=7` |
| `ordering` | `?ordering=-total_amount` |

---

### 8.9 Payment Disbursement

After an invoice is fully paid, the admin disburses the collected amount equally among all staff who worked on the job. One `PaymentDisbursement` record is created per staff member.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/billing/invoices/<id>/disburse/` | Admin | Split collected amount equally to all assigned staff |
| `GET` | `/api/v1/billing/disbursements/` | Admin | List all disbursement records |

#### Disburse payment

```
POST /api/v1/billing/invoices/5/disburse/
```

No request body required.

**Business rules:**
- Invoice must have `payment_status=paid`
- Disbursement is idempotent — calling twice returns `400`

**Response `201`:**
```json
{
  "message": "Payment disbursed to 8 staff member(s).",
  "disbursements": [
    {
      "id": 1,
      "invoice": 5,
      "job_title": "3-Bedroom Move — Westlands to Karen",
      "staff": 5,
      "staff_name": "John Mwangi",
      "staff_email": "staff05@emovers.co.ke",
      "amount": "3450.00",
      "status": "disbursed",
      "disbursed_at": "2026-05-22T11:00:00Z",
      "transaction_ref": "SIM-DSB-1716372000-A1B2C3D4"
    }
  ]
}
```

Each disbursed staff member also receives a `payment_disbursed` notification.

#### Query parameters for `GET /api/v1/billing/disbursements/`

| Param | Example |
|---|---|
| `invoice` | `?invoice=5` |
| `staff` | `?staff=7` |
| `status` | `?status=disbursed` |

---

### 8.10 Reviews

Post-job reviews submitted by the supervisor about each mover. Reviews drive the `recommendation_score` that controls auto-allocation priority.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/reviews/create/` | Staff (supervisor) | Submit a single review |
| `POST` | `/api/v1/reviews/bulk-create/` | Staff (supervisor) | Submit all reviews for a job in one request (recommended) |
| `GET` | `/api/v1/reviews/` | Admin | All reviews in the system |
| `GET` | `/api/v1/reviews/my-reviews/` | Staff | Reviews received about yourself |
| `GET` | `/api/v1/reviews/staff/<id>/summary/` | Admin + Staff | Full review summary for a staff member |
| `GET` | `/api/v1/reviews/job/<id>/` | Admin + Staff | All reviews for a specific job |

#### Business rules

1. Job must be `completed`
2. Reviewer must be the `supervisor` on that job
3. Reviewee must be a `mover` (not supervisor) on the same job
4. One review per `(job, reviewee, category)` — `400` on duplicate

#### Bulk create (recommended workflow)

```
POST /api/v1/reviews/bulk-create/
```

```json
{
  "job_id": 7,
  "reviews": [
    { "reviewee_id": 8,  "category": "overall",         "rating": 5, "comment": "Excellent work." },
    { "reviewee_id": 8,  "category": "punctuality",     "rating": 5 },
    { "reviewee_id": 8,  "category": "care_of_goods",   "rating": 4 },
    { "reviewee_id": 11, "category": "overall",         "rating": 3, "comment": "Average effort." },
    { "reviewee_id": 11, "category": "teamwork",        "rating": 4 },
    { "reviewee_id": 11, "category": "communication",   "rating": 3 }
  ]
}
```

The batch is processed item by item. Successful items return in `created`; failed items return in `errors` with a reason. If some succeed and some fail, HTTP `207 Multi-Status` is returned.

#### Review category values

| Value | What it measures |
|---|---|
| `overall` | General performance |
| `punctuality` | Arrived on time, met schedule |
| `teamwork` | Collaborated with the crew |
| `care_of_goods` | Handled items carefully |
| `physical_fitness` | Managed physically demanding tasks |
| `communication` | Communicated clearly with team and client |

#### Rating scale

| Value | Label |
|---|---|
| `1` | Very Poor |
| `2` | Poor |
| `3` | Average |
| `4` | Good |
| `5` | Excellent |

---

### 8.11 Notifications

In-app notification inbox. All notifications are scoped to the authenticated user — staff only see their own.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/notifications/` | Auth | List own notifications, newest first |
| `GET` | `/api/v1/notifications/unread-count/` | Auth | Badge count: `{ "count": N }` |
| `POST` | `/api/v1/notifications/mark-all-read/` | Auth | Mark all own notifications as read |
| `PATCH` | `/api/v1/notifications/<id>/read/` | Auth | Mark a single notification as read |

#### Unread count (for badge)

```
GET /api/v1/notifications/unread-count/
```

**Response `200`:**
```json
{ "count": 3 }
```

#### Filter by read status

```
GET /api/v1/notifications/?is_read=false
```

#### Notification type values

| Type | When it fires |
|---|---|
| `application_approved` | Staff member is approved for a job |
| `application_rejected` | Staff member is not selected for a job |
| `job_team_announced` | Full team list shared after approval |
| `attendance_reminder` | (extensible — send via admin or Celery task) |
| `payment_disbursed` | Staff member's share has been disbursed |
| `review_received` | Staff member received a new review |
| `general` | Admin-generated announcements |

#### Sample notification object

```json
{
  "id": 7,
  "notification_type": "application_approved",
  "type_display": "Application Approved",
  "title": "You're in! — 3-Bedroom Move — Westlands to Karen",
  "body": "You have been selected for '3-Bedroom Move...' on 2026-05-20.\nYour team: John Mwangi, Alice Kamau, ...\nPlease confirm your attendance on the morning of the move.",
  "is_read": false,
  "job": 7,
  "job_title": "3-Bedroom Move — Westlands to Karen",
  "created_at": "2026-05-10T14:30:00Z"
}
```

---

### 8.12 Reports

All report endpoints are **Admin only**. Staff receive `403 Forbidden`.

| Method | Endpoint | Query Params | Description |
|---|---|---|---|
| `GET` | `/api/v1/reports/dashboard/` | `?days=30` | Key KPIs across all modules |
| `GET` | `/api/v1/reports/jobs/` | `?days=30` | Job status, daily completions, move-size distribution |
| `GET` | `/api/v1/reports/billing/` | `?days=30` | Revenue totals, payment methods, monthly trend, top unpaid |
| `GET` | `/api/v1/reports/staff-performance/` | `?available_only=true` | All staff ranked by `recommendation_score` |
| `GET` | `/api/v1/reports/fleet/` | — | Fleet utilization, on-job trucks, service-due trucks |
| `GET` | `/api/v1/reports/attendance/` | `?days=30` | Confirmation rates per job and per staff member |
| `GET` | `/api/v1/reports/applications/` | `?days=30` | Application volume, approval rate, open applications by job |

**`?days=N`** controls the lookback window (1–365, default 30).

#### Dashboard response shape

```json
{
  "window_days": 30,
  "staff": { "total_active": 15, "available": 12, "on_job": 3 },
  "fleet":  { "total": 6, "available": 4, "on_job": 2, "maintenance": 0 },
  "jobs": {
    "total": 25,
    "pending": 4, "assigned": 2, "in_progress": 1, "completed": 15, "cancelled": 3,
    "unassigned_needing_attention": 2,
    "created_last_30_days": 8
  },
  "billing": {
    "total_invoiced": "348000.00",
    "total_collected": "280000.00",
    "total_outstanding": "68000.00",
    "unpaid_invoices": 5
  },
  "customers": { "total": 42, "new_last_30_days": 6 }
}
```

#### Attendance report response shape

```json
{
  "window_days": 30,
  "totals": {
    "total_records": 88,
    "confirmed": 81,
    "absent": 7,
    "confirmation_rate_percent": 92.05
  },
  "per_job": [
    {
      "job__id": 7,
      "job__title": "3-Bedroom Move — Westlands to Karen",
      "job__scheduled_date": "2026-05-20",
      "confirmed": 8,
      "absent": 0,
      "total": 8
    }
  ],
  "top_absent_staff": [
    { "staff__id": 12, "staff__first_name": "Mark", "staff__last_name": "Otieno", "absent_count": 2 }
  ]
}
```

#### Applications report response shape

```json
{
  "window_days": 30,
  "total_applications": 47,
  "status_breakdown": [
    { "status": "approved",  "count": 24 },
    { "status": "applied",   "count": 8  },
    { "status": "rejected",  "count": 12 },
    { "status": "withdrawn", "count": 3  }
  ],
  "approval_rate_percent": 51.06,
  "top_applicants": [ ... ],
  "jobs_with_open_applications": [ ... ]
}
```

---

## 9. Error Response Format

All errors follow the same structure:

```json
{ "error": "Human-readable description of what went wrong." }
```

Validation errors from serializers use DRF's default format:

```json
{
  "field_name": ["This field is required."],
  "another_field": ["Ensure this value is greater than or equal to 1."]
}
```

| HTTP Status | When it occurs |
|---|---|
| `400 Bad Request` | Validation error, business rule violation |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | Authenticated but insufficient role |
| `404 Not Found` | Resource does not exist or is not owned by the user |
| `207 Multi-Status` | Bulk review create — some items succeeded, some failed |

---

## 10. Recommendation Score Algorithm

The `recommendation_score` drives which staff are auto-allocated and in what order applicants are ranked.

```
average_rating       = mean of all ratings received across all reviews
recommendation_score = (average_rating / 5.0) × 0.8 + 0.2
```

| Scenario | `average_rating` | `recommendation_score` |
|---|---|---|
| No reviews yet | 0 | **1.000** (fresh staff get max score — give everyone a chance) |
| All 5-star reviews | 5.00 | **1.000** |
| All 4-star reviews | 4.00 | **0.840** |
| All 3-star reviews | 3.00 | **0.680** |
| All 1-star reviews | 1.00 | **0.360** |

Score range: `0.200` (worst) to `1.000` (best). Even the lowest-scoring staff retain a base chance of assignment when no better candidates are available.

Scores update immediately after every review save via Django signal — no manual recalculation needed.

---

## 11. Running Tests

The integration test suite covers all 110 scenarios end-to-end against a live SQLite test DB. It seeds fresh data before every run.

```bash
cd e_movers_backend
python integration_tests.py
```

Expected output:
```
--- AUTH ---
  PASS  login_admin
  ...
============================================================
  Results: 110/110 passed  |  0 failed
============================================================
  All tests passed.
```

Exit code `0` on success, `1` on any failure.

---

## 12. Database Reset & Re-seed

### Windows

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

### macOS / Linux

```bash
rm db.sqlite3
find . -path "*/migrations/0*.py" -delete
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
```

---

## 13. Deployment Notes

| Setting | Action required |
|---|---|
| `SECRET_KEY` | Replace the insecure dev key with a strong random value |
| `DEBUG` | Set to `False` |
| `ALLOWED_HOSTS` | Set to your domain(s) |
| `DATABASES` | Switch from SQLite to PostgreSQL |
| `CORS_ALLOW_ALL_ORIGINS` | Set to `False`; specify `CORS_ALLOWED_ORIGINS` |

**Collect static files:**
```bash
python manage.py collectstatic
```

**Production server:**
```bash
gunicorn e_movers.wsgi:application --workers 4 --bind 0.0.0.0:8000
```

Serve static files and proxy to gunicorn via **nginx**.

**Environment variables to set in production:**

```bash
DJANGO_SECRET_KEY=<strong-random-key>
DJANGO_DEBUG=False
DATABASE_URL=postgres://user:password@host:5432/emovers
ALLOWED_HOSTS=api.yourdomain.com
CORS_ALLOWED_ORIGINS=https://app.yourdomain.com
```
