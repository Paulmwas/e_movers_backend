# Smartmovers Backend API

> **Django REST Framework** backend for the Smartmovers moving company management system.
> Internal operational tool for admins and mover staff — not a customer-facing booking platform.

---

## Table of Contents

0. [Updates](#updates)
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
14. [Frontend Integration Guide](#14-frontend-integration-guide)

---

## Updates

> **Last updated: 2026-06-07**

### What changed — 2026-06-07

#### 1. Email notification to all staff on auto-allocation

Whenever a job is **auto-allocated**, every assigned staff member (supervisor and all movers) now receives both an **in-app notification** and a branded **HTML email** confirming their assignment.

- Notification type: `job_allocated`
- Subject: `"You've been assigned to: <job title>"`
- Email includes: job title, scheduled date, pickup address, drop-off address
- No admin action required — fires automatically at the end of `POST /jobs/:id/auto-allocate/`

**Frontend action:** Add `job_allocated` to the notification bell's type-display map:

| Type | Label |
|---|---|
| `job_allocated` | Job Assigned (Auto) |

---

#### 2. Invoice now shows move size

Every invoice response now includes two new read-only fields:

```json
{
  "move_size": "three_bedroom",
  "move_size_display": "3 Bedroom",
  ...
}
```

**Frontend action:** On the invoice detail screen, show the move size (e.g. "3 Bedroom") prominently — it helps identify which pricing tier the invoice was calculated on.

---

#### 3. Staff charge and truck charge are no longer zero on bedroom invoices

Previously `staff_charge` and `truck_charge` were always `"0.00"` for bedroom jobs. They now reflect the actual cost allocation:

| Field | Value |
|---|---|
| `staff_charge` | `500 × assigned_staff_count` |
| `truck_charge` | `1,500 × assigned_truck_count` |

These are **informational breakdown fields** — they show how the revenue is allocated. The customer-facing **total is unchanged**: `total_amount = base_charge + distance_charge`.

**Sample invoice for a 3-bedroom move at 15 km with 4 staff and 1 truck:**

```json
{
  "move_size": "three_bedroom",
  "move_size_display": "3 Bedroom",
  "base_charge": "20000.00",
  "distance_charge": "6000.00",
  "staff_charge": "2000.00",
  "truck_charge": "1500.00",
  "subtotal": "26000.00",
  "tax_rate": "0.0000",
  "tax_amount": "0.00",
  "total_amount": "26000.00"
}
```

**Frontend action:**
- **Remove** any logic that hides `staff_charge` / `truck_charge` when zero.
- Render them as an **"Operational Breakdown"** sub-section (e.g. "Staff payout: KES 2,000 · Truck cost: KES 1,500") separate from the customer price line.
- `total_amount` is still what the customer pays — do not add `staff_charge + truck_charge` to the displayed total.

---

#### 4. Auto-allocate response includes full truck details

The response from `POST /jobs/:id/auto-allocate/` now includes the complete truck object for each allocated truck (previously the response could return empty truck details due to a stale cache):

```json
{
  "message": "Job allocated successfully.",
  "job": {
    ...
    "trucks": [
      {
        "id": 1,
        "truck": 2,
        "plate_number": "KDB 002A",
        "truck_type": "Medium Truck",
        "make": "Isuzu",
        "model": "NPR",
        "capacity_tons": "3.50",
        "allocation_method": "AUTO",
        "allocation_method_display": "Auto",
        "assigned_at": "2026-06-07T08:00:00Z"
      }
    ]
  }
}
```

**Frontend action:** On the post-allocation success screen, display the allocated truck(s) with plate number, make, model, and capacity. No API re-fetch needed — the `trucks` array in the response is now complete.

---

#### 5. Email templates updated to Smartmovers branding

All system emails (assignment confirmation, payment disbursed) now show **Smartmovers** in the header instead of the old "E-Movers" label. No frontend action needed.

---

### What changed — 2026-06-05

#### 1. Product renamed to **Smartmovers**

All user-facing documents (quote PDFs, emails, notifications) now use the brand name **Smartmovers**. Internal code paths and repo names are unchanged.

---

#### 2. Auto-allocation no longer hardcodes 11 staff

**Before:** Auto-allocate always assigned 10 movers + 1 supervisor = **11 staff**, regardless of the job's `requested_staff_count`.

**Now:** Auto-allocate reads `job.requested_staff_count` and `job.requested_truck_count` as defaults. The override body fields are now **optional**:

```
POST /api/v1/jobs/<id>/auto-allocate/
```

```json
{}
```
_No body needed — uses the job's own requirements._

Or override explicitly:
```json
{ "num_movers": 3, "num_trucks": 1 }
```

`num_movers` = number of movers **excluding the supervisor**. Total staff assigned = `num_movers + 1`.

**Frontend action:** If you were sending `{ "num_movers": 10, "num_trucks": 1 }` unconditionally, stop doing that. Send an empty body `{}` or omit the fields to let the job drive the count.

---

#### 3. New endpoint — Change Team Leader

Admin can now swap the supervisor on any ASSIGNED or IN_PROGRESS job. The target staff member must already be assigned as a mover on that job — it is a role swap, not a fresh assignment.

```
PATCH /api/v1/jobs/<id>/change-supervisor/
Authorization: Bearer <admin_token>
Content-Type: application/json

{ "staff_id": 7 }
```

**Response `200`:**
```json
{
  "message": "Team leader updated successfully.",
  "job": { ... }
}
```

**Error cases:**
- `400` — job is not ASSIGNED or IN_PROGRESS
- `400` — target staff is already the supervisor
- `400` — target staff is not assigned to this job as a mover

---

#### 4. Truck assignments now include `allocation_method`

The truck objects inside `job.trucks` now carry two new fields:

```json
{
  "id": 3,
  "truck": 2,
  "plate_number": "KDB 002A",
  "truck_type": "Medium Truck",
  "make": "Isuzu",
  "model": "NPR",
  "capacity_tons": "3.50",
  "allocation_method": "auto",
  "allocation_method_display": "Auto",
  "assigned_at": "2026-06-05T08:00:00Z"
}
```

| Value | Meaning |
|---|---|
| `auto` | Assigned by the auto-allocate algorithm |
| `manual` | Assigned manually via `POST /jobs/:id/assign-trucks/` |

**Frontend action:** Display a badge or label on each truck showing whether it was auto or manually assigned.

---

#### 5. Staff profile — ratings and scores removed from API

`average_rating`, `total_reviews`, and `recommendation_score` are **no longer returned** by the staff profile or user API endpoints. The scores still exist internally and drive auto-allocation, but they are not exposed.

**Affected endpoints:**
- `GET /api/v1/users/<id>/staff-profile/`
- `GET /api/v1/users/`
- `GET /api/v1/users/available-staff/`

**Frontend action:** Remove any display of `average_rating`, `recommendation_score`, or star ratings from the staff management screens.

---

#### 6. New move sizes — 4, 5, and 6 Bedroom

Three new `move_size` values are now accepted:

| Value | Label |
|---|---|
| `four_bedroom` | 4 Bedroom |
| `five_bedroom` | 5 Bedroom |
| `six_bedroom` | 6 Bedroom |

**Frontend action:** Add these options to the job creation / edit form's move size dropdown.

---

#### 7. New pricing model — bedroom + distance (replaces old formula)

The invoice calculation for bedroom moves is now completely different. The old base + per-km + per-staff + per-truck + VAT formula **no longer applies to bedroom jobs**.

**New formula for 1–6 bedroom moves:**

| Move size | Bedroom charge (KES) |
|---|---:|
| 1 Bedroom | 10,000 |
| 2 Bedroom | 14,000 |
| 3 Bedroom | 20,000 |
| 4 Bedroom | 24,000 |
| 5 Bedroom | 28,000 |
| 6 Bedroom | 32,000 |

| Distance | Distance charge (KES) |
|---|---:|
| Below 10 km | 3,000 |
| 10 – 20 km | 6,000 |
| 20 – 30 km | 9,000 |
| 30 – 40 km | 12,000 |
| Above 40 km | 12,000 (capped) |

**Total = bedroom charge + distance charge** (no VAT, no staff charge, no truck charge for bedroom moves)

Studio, office_small, and office_large jobs continue to use the legacy formula.

**Invoice response fields — what to display:**

```json
{
  "base_charge": "20000.00",
  "distance_charge": "6000.00",
  "staff_charge": "0.00",
  "truck_charge": "0.00",
  "subtotal": "26000.00",
  "tax_rate": "0.0000",
  "tax_amount": "0.00",
  "total_amount": "26000.00"
}
```

**Frontend action:** Update the invoice detail screen to render the new breakdown correctly. `staff_charge`, `truck_charge`, and `tax_amount` will be `0.00` for bedroom jobs — consider hiding those rows when zero.

---

#### 8. Disbursement model — flat KES 500 per staff + company profit

**Before:** `amount_paid` was split equally among all staff.

**Now:** Each staff member always receives a flat **KES 500**. The remainder is recorded as `company_profit` on the invoice.

```
company_profit = amount_paid − (500 × staff_count)
```

**Invoice now includes `company_profit`:**

```json
{
  "amount_paid": "26000.00",
  "company_profit": "24000.00",
  ...
}
```

**Disbursement response — each record will always show `amount: "500.00"`:**

```json
{
  "message": "Payment disbursed to 4 staff member(s).",
  "disbursements": [
    {
      "staff_name": "John Mwangi",
      "amount": "500.00",
      "status": "disbursed"
    }
  ]
}
```

**Frontend action:**
- On the disbursement confirmation screen, show **KES 500 per staff** as a fixed amount.
- On the invoice detail / billing report, show a **Company Profit** line using `invoice.company_profit`.

---

#### 9. Reports — default window extended + `?all=true` + company profit

| Change | Detail |
|---|---|
| Default `?days` | Changed from **30** to **365** — reports now show a full year by default |
| `?all=true` | Pass this to any report endpoint to bypass the date filter entirely |
| `company_profit` | Added to the billing report `revenue_totals` object |

**Billing report — updated `revenue_totals` shape:**

```json
{
  "revenue_totals": {
    "total_invoiced": "520000.00",
    "total_collected": "480000.00",
    "total_outstanding": "40000.00",
    "total_company_profit": "430000.00"
  }
}
```

**Frontend action:**
- Add a **Company Profit** stat card or chart tile on the billing report / dashboard screen using `total_company_profit`.
- Optionally add an "All time" toggle that appends `?all=true` to report API calls.

---

#### 10. New public endpoint — Full Price Guide (PDF)

Clicking "Get a Quote" on the homepage downloads a **Smartmovers-branded PDF price guide** showing all pricing options at a glance. No form input or login required.

```
GET /api/v1/billing/quote/
(no Authorization header, no request body)
```

**Response:** `application/pdf` file — `smartmovers_pricing.pdf`

The PDF contains three sections:
1. **Move Size Charges** — base price for each bedroom count (1–6 bedrooms)
2. **Distance Charges** — price bracket per km band (< 10 km up to > 40 km)
3. **Complete Price Matrix** — every move size × every distance band in a grid so the customer can find their exact total at a glance

**Frontend implementation — single button, no form needed:**

```js
// Homepage "Get a Quote" button
async function downloadPriceGuide() {
  const response = await fetch(`${API_BASE}/billing/quote/`, {
    method: 'GET',
  })

  if (!response.ok) return

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'smartmovers_pricing.pdf'
  link.click()
  URL.revokeObjectURL(url)
}
```

Or even simpler — just use an anchor tag that opens the URL directly:

```html
<a href="https://e-movers-backend.onrender.com/api/v1/billing/quote/" download>
  Get a Quote
</a>
```

---

### What changed — 2026-05-05

#### 1. Public staff availability form (no login required)

Staff no longer need to log in to indicate availability for a job. Two new public endpoints allow staff to apply or withdraw using only their email address.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/jobs/public/` | None | Browse all PENDING jobs open for applications |
| `POST` | `/api/v1/jobs/<id>/public-apply/` | None | Confirm availability — creates a JobApplication |
| `DELETE` | `/api/v1/jobs/<id>/public-apply/` | None | Withdraw availability |

**How it works (public apply):**

```
POST /api/v1/jobs/3/public-apply/
Content-Type: application/json

{ "email": "staff05@emovers.co.ke" }
```

Response `201`:
```json
{
  "message": "Availability confirmed. The admin will review your application.",
  "application": {
    "id": 14,
    "job": 3,
    "job_title": "Wangari 3-Bedroom Move — South C to Karen",
    "job_scheduled_date": "2026-05-13",
    "staff_name": "Joseph Waweru",
    "status": "applied",
    "applied_at": "2026-05-05T09:00:00Z"
  }
}
```

**Withdraw:**
```
DELETE /api/v1/jobs/3/public-apply/
{ "email": "staff05@emovers.co.ke" }
```

All the same business rules apply as the authenticated endpoint (deadline, max applicants, job must be pending, one application per staff per job).

**Public job listing** (`GET /api/v1/jobs/public/`) returns safe fields only — no customer contact details:
```json
[
  {
    "id": 3,
    "title": "Wangari 3-Bedroom Move — South C to Karen",
    "move_size": "three_bedroom",
    "move_size_display": "3 Bedroom",
    "pickup_address": "21 South C, Nairobi",
    "dropoff_address": "45 Karen Road, Nairobi",
    "estimated_distance_km": "15.00",
    "scheduled_date": "2026-05-13",
    "scheduled_time": null,
    "requested_staff_count": 8,
    "application_deadline": null,
    "max_applicants": 20,
    "applicant_count": 9,
    "is_open_for_applications": true,
    "special_instructions": "Antique furniture — do not stack."
  }
]
```

#### 2. Admin workflow for approving availability

The admin flow remains unchanged — the admin views applicants ranked by `recommendation_score` and either:

**Option A — Manual approval (picks best candidates):**
```
GET  /api/v1/jobs/<id>/applications/           → see all applicants ranked by score
POST /api/v1/jobs/<id>/approve-applications/   → approve subset + designate supervisor
```

**Option B — Auto-allocate by review score:**
```
POST /api/v1/jobs/<id>/auto-allocate/
{ "num_movers": 6, "num_trucks": 1 }
```
Auto-allocation selects the top-rated available staff ordered by `recommendation_score DESC`. The highest-scoring candidate becomes the supervisor.

#### 3. JobApplication visible in Django admin

`JobApplication` is now registered in the admin panel:
- Listed under **Jobs > Job Applications** with status, timestamps, and reviewer
- Also appears as an inline tab inside each Job's admin detail page
- Admins can filter by status (`applied`, `approved`, `rejected`, `withdrawn`) and search by job title or staff name

#### 4. Expanded seed data

`python manage.py seed_data` now creates:

| Entity | Before | Now |
|---|---|---|
| Staff | 15 | 20 |
| Customers | 10 | 15 |
| Trucks | 6 | 8 |
| Jobs total | 8 | 13 |
| Pending (no applications) | 2 | 3 |
| Pending (with applications) | 0 | 3 — ready for admin to approve |
| Assigned | 2 | 2 |
| In progress | 1 | 1 |
| Completed | 2 | 3 — each with invoice, payment, reviews |
| Cancelled | 0 | 1 |

The 3 "pending with applications" jobs demonstrate the full public-form flow: staff have already submitted availability and the admin can open the applications list and approve.

#### 5. Bug fix — auto-allocate no-op removed

`auto_allocate_job` contained a harmless but misleading `User.objects.filter(...).update()` call with no arguments. It has been removed.

---

### What changed — 2026-05-17

#### 1. Attendance confirmation removed (no more PIN)

Staff no longer confirm attendance via PIN. The generate-PIN and confirm-attendance endpoints have been removed. Admins can still view the attendance list for a job and mark staff absent manually.

**Removed endpoints:**
- ~~`POST /api/v1/attendance/generate-pin/<job_id>/`~~
- ~~`POST /api/v1/attendance/confirm/`~~

**Remaining attendance endpoints:**

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/attendance/<job_id>/` | Admin + Staff | View attendance records for a job |
| `POST` | `/api/v1/attendance/<job_id>/mark-absent/` | Admin | Mark a staff member as absent |

#### 2. PDF download for job team roster

Admins and staff can now download a PDF listing all team members assigned to a move.

```
GET /api/v1/jobs/<id>/team-pdf/
Authorization: Bearer <token>
```

Returns a PDF file (`application/pdf`) with:
- Job title, customer name, scheduled date and time
- Pickup and drop-off addresses, job status
- Numbered team roster (supervisor listed first, then movers)

**Frontend usage:**

```js
// Trigger a file download in the browser
const response = await api.get(`/jobs/${jobId}/team-pdf/`, { responseType: 'blob' })
const url = URL.createObjectURL(response.data)
const link = document.createElement('a')
link.href = url
link.download = `team_${jobId}.pdf`
link.click()
URL.revokeObjectURL(url)
```

Access: Admin (`mover-admin`) and Staff (`mover-staff`). Returns `404` if the job does not exist.

#### 3. SMTP email notifications

Two events now send a real email in addition to the existing in-app notification:

| Trigger | Who receives email | Subject |
|---|---|---|
| Admin approves applications (job assigned) | All approved staff | `You're in! — {job title}` |
| Admin disburses payment | All assigned staff | `Payment Received — {job title}` |

**application_approved email** — styled HTML with blue header:
- Job title, scheduled date & time, pickup and drop-off addresses
- Full team member list (pulled from the existing approval notification body)

**payment_disbursed email** — styled HTML with green header:
- "Your payment of KES X,XXX for '...' has been disbursed."
- Thank-you closing

Emails are sent via Django's built-in SMTP backend — no new packages required. Configure the SMTP credentials in `.env` (see Deployment Notes). If `EMAIL_HOST_USER` is not set, emails are silently skipped and in-app notifications still work normally.

To print emails to the terminal during local development instead of sending:
```bash
# .env (dev only)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

#### 4. Supervisor review notification on job completion

When a job is marked as **completed**, the supervisor automatically receives a `review_pending` in-app notification listing all movers they must rate. No admin action is needed — the notification fires via signal as soon as the job status transitions to `completed`.

**What the supervisor receives:**

```json
{
  "notification_type": "review_pending",
  "title": "Please review your team — 3-Bedroom Move — Westlands to Karen",
  "body": "The job '3-Bedroom Move — Westlands to Karen' has been completed. Please submit your performance reviews for the following team members: John Mwangi, Alice Kamau, Peter Njoroge.",
  "job": 7
}
```

**Supervisor review flow:**
1. Job completes → `review_pending` notification appears in supervisor's inbox
2. Supervisor fetches team members to review: `GET /api/v1/reviews/job/<id>/` (see who has/hasn't been reviewed)
3. Supervisor submits reviews: `POST /api/v1/reviews/bulk-create/`
4. Each mover receives a `review_received` notification
5. Recommendation scores update immediately

**Frontend — show a "Review your team" prompt when `review_pending` notification is present:**
```js
// On the job detail page, check if a pending review notification exists
const notifications = await api.get('/notifications/?is_read=false')
const reviewPending = notifications.data.results.find(
  n => n.notification_type === 'review_pending' && n.job === jobId
)
if (reviewPending) {
  // Show "Rate your team" button / banner
}
```

### What changed — 2026-05-18

#### 1. SMTP email configuration finalised

- `DEFAULT_FROM_EMAIL` must equal `EMAIL_HOST_USER` — Gmail rejects messages where the sender doesn't match the authenticated account.
- Gmail App Passwords must be stored **without spaces** in `.env`. Google displays them as `xxxx xxxx xxxx xxxx` for readability; strip the spaces before pasting: `xxxxxxxxxxxxxxxx`.
- Email env vars are documented in `.env.example`. Copy them to your real `.env` and fill in your credentials.

---

## 1. Overview

E-Movers manages the full lifecycle of a moving job:

| Phase | Who | What happens |
|---|---|---|
| Job creation | Admin | Creates a job with location, schedule, and move size |
| Application | Staff | Browse pending jobs and apply; admin caps and deadlines enforced |
| Approval | Admin | Reviews applicants, approves a subset, designates supervisor |
| Notification | System | Approved staff get team list; rejected staff get a notice |
| Attendance | Admin | Admin marks absent staff manually; no PIN required |
| Execution | Supervisor | Starts job → completes job |
| Billing | Admin | Generates invoice → records simulated payment |
| Disbursement | Admin | Splits collected amount equally among all assigned staff |
| Review | Supervisor | Rates each mover across multiple categories |
| Next cycle | System | Recommendation scores update instantly; best-rated staff surface first in auto-allocation |

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 + Django REST Framework 3.17 |
| Auth | JWT — `djangorestframework-simplejwt` 5.5 |
| Filtering | `django-filter` 25.1 |
| CORS | `django-cors-headers` 4.9 |
| Database | SQLite (dev) / PostgreSQL (production) |
| PDF export | `reportlab` 4.2 |
| Email | Django built-in SMTP (`django.core.mail`) |

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
├── notifications/          # In-app notification inbox + SMTP email dispatch
├── attendance/             # Attendance records (absent marking; no PIN)
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
git clone https://github.com/Paulmwas/e_movers_backend
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
git clone https://github.com/Paulmwas/e_movers_backend
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
| Staff 01–20 | `staff01@emovers.co.ke` … `staff20@emovers.co.ke` | `Staff1234!` | `mover-staff` |

The seed command creates 20 staff, 15 customers, 8 trucks, and 13 jobs in various lifecycle stages (including 3 jobs pre-loaded with staff availability applications), plus invoices, payments, and reviews.

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
| Mover Staff | `mover-staff` | Apply for jobs, start/complete assigned jobs, submit reviews (supervisor), view own notifications and reviews |

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

5.  Morning of move — Admin marks no-shows  POST /api/v1/attendance/<id>/mark-absent/
      └─ AttendanceRecord(status=absent) created for each no-show

6.  Supervisor starts job            POST /api/v1/jobs/<id>/status/  {"action": "start"}
      └─ Job status → "in_progress"

7.  Admin generates invoice          POST /api/v1/billing/invoices/generate/
      └─ Costs calculated: base + distance + staff + truck + 16% VAT

8.  Supervisor completes job         POST /api/v1/jobs/<id>/status/  {"action": "complete"}
      └─ Job status → "completed"
      └─ All staff released: is_available = True
      └─ All trucks released: status = "available"
      └─ [SIGNAL] Supervisor receives review_pending notification with team list

9.  Admin records payment            POST /api/v1/billing/invoices/<id>/pay/
      └─ Simulated payment (cash / M-Pesa / bank / card)
      └─ Partial payments supported; invoice tracks balance_due

10. Admin disburses to staff         POST /api/v1/billing/invoices/<id>/disburse/
      └─ Invoice must be fully PAID first
      └─ amount_paid split equally among all assigned staff
      └─ One PaymentDisbursement record per staff member
      └─ [NOTIFICATION] Each staff member notified of their payment

11. Supervisor reviews movers        POST /api/v1/reviews/bulk-create/
      └─ Ratings per (job, reviewee, category)
      └─ [SIGNAL] recommendation_score recalculated immediately per mover

12. Next job cycle
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
| `POST` | `/api/v1/jobs/<id>/auto-allocate/` | Admin | Auto-assign staff + trucks (defaults to job's requested counts) |
| `PATCH` | `/api/v1/jobs/<id>/change-supervisor/` | Admin | Swap the team leader on an assigned/in-progress job |
| `POST` | `/api/v1/jobs/<id>/assign-staff/` | Admin | Manually assign specific staff |
| `POST` | `/api/v1/jobs/<id>/assign-trucks/` | Admin | Manually assign specific trucks |
| `POST` | `/api/v1/jobs/<id>/status/` | Admin + Staff | Transition job through status machine |
| `GET` | `/api/v1/jobs/<id>/team-pdf/` | Admin + Staff | Download PDF team roster for a job |

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

`studio` · `one_bedroom` · `two_bedroom` · `three_bedroom` · `four_bedroom` · `five_bedroom` · `six_bedroom` · `office_small` · `office_large`

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

Body is **optional**. When omitted the job's own `requested_staff_count` and `requested_truck_count` are used:

```json
{}
```

To override the defaults:
```json
{
  "num_movers": 3,
  "num_trucks": 2
}
```

`num_movers` is the number of movers **excluding the supervisor** — total staff assigned = `num_movers + 1`.

Selects active, available staff ordered by `recommendation_score DESC`. The top candidate becomes supervisor; the rest become movers. Safe to call multiple times — re-running releases the previous assignment first.

---

#### Change team leader (new)

```
PATCH /api/v1/jobs/<id>/change-supervisor/
```

```json
{ "staff_id": 7 }
```

The target staff member must already be assigned to the job as a mover. The current supervisor is demoted to mover, and the target mover is promoted to supervisor.

**Allowed on:** `assigned` and `in_progress` jobs only.

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

Admin-managed attendance records. The admin views the assigned team and marks any no-shows as absent. There is no PIN or staff self-confirmation step.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/attendance/<job_id>/` | Admin + Staff | Full attendance list for a job |
| `POST` | `/api/v1/attendance/<job_id>/mark-absent/` | Admin | Manually mark a staff member as absent |

#### View attendance for a job

```
GET /api/v1/attendance/7/
```

Returns all attendance records (absent entries) for the job.

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
| `absent` | Marked absent by admin |

---

### 8.8 Billing — Invoices & Payments

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/v1/billing/quote/` | **Public** | Download the full Smartmovers price guide PDF |
| `GET` | `/api/v1/billing/invoices/` | Admin + Staff | List all invoices |
| `POST` | `/api/v1/billing/invoices/generate/` | Admin | Calculate costs and create or refresh an invoice |
| `GET` / `PATCH` | `/api/v1/billing/invoices/<id>/` | Admin + Staff | Invoice detail with full payment history |
| `POST` | `/api/v1/billing/invoices/<id>/pay/` | Admin | Record a simulated payment |
| `GET` | `/api/v1/billing/payments/` | Admin + Staff | Full payment history |

#### Cost formula (all amounts in KES)

**Bedroom moves (1–6 bedrooms):**

| Move size | Bedroom charge | Distance < 10 km | 10–20 km | 20–30 km | 30–40 km | > 40 km |
|---|---:|---:|---:|---:|---:|---:|
| 1 Bedroom | 10,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |
| 2 Bedroom | 14,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |
| 3 Bedroom | 20,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |
| 4 Bedroom | 24,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |
| 5 Bedroom | 28,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |
| 6 Bedroom | 32,000 | +3,000 | +6,000 | +9,000 | +12,000 | +12,000 |

```
Total = bedroom_charge + distance_charge   (no VAT, no per-staff, no per-truck)
```

**Studio / office moves (legacy formula):**

```
Base charge      =  2,000
Distance charge  =    100  ×  estimated_distance_km
Staff charge     =    500  ×  assigned_staff_count
Truck charge     =  1,500  ×  assigned_truck_count
Subtotal         =  sum of above
VAT (16%)        =  subtotal × 0.16
Total            =  subtotal + VAT
```

The formula runs fresh every time `generate/` is called. If assignments change before the job starts, call `generate/` again to get the updated amount.

> **Invoice breakdown for bedroom jobs:** `base_charge` + `distance_charge` = `total_amount` (what the customer pays). `staff_charge` (500 × staff) and `truck_charge` (1,500 × trucks) are **informational only** — do not add them to the displayed total. `tax_amount` is always `"0.00"` for bedroom jobs — hide it.

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

After an invoice is fully paid, the admin disburses **KES 500 flat** to each assigned staff member. The remainder is recorded as **company profit** on the invoice.

```
staff_payout   = 500 × staff_count
company_profit = amount_paid − staff_payout
```

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/v1/billing/invoices/<id>/disburse/` | Admin | Pay each staff member KES 500; remainder → company profit |
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
  "message": "Payment disbursed to 4 staff member(s).",
  "disbursements": [
    {
      "id": 1,
      "invoice": 5,
      "job_title": "3-Bedroom Move — Westlands to Karen",
      "staff": 5,
      "staff_name": "John Mwangi",
      "staff_email": "staff05@emovers.co.ke",
      "amount": "500.00",
      "status": "disbursed",
      "disbursed_at": "2026-06-05T11:00:00Z",
      "transaction_ref": "SIM-DSB-1749115200-A1B2C3D4"
    }
  ]
}
```

After disbursement, `invoice.company_profit` holds the net retained amount. Each disbursed staff member also receives a `payment_disbursed` notification.

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
| `application_approved` | Staff member is approved for a job (manual approval flow) |
| `application_rejected` | Staff member is not selected for a job |
| `job_team_announced` | Full team list shared after approval |
| `job_allocated` | Staff member is automatically assigned via auto-allocate |
| `attendance_reminder` | (extensible — send via admin or Celery task) |
| `payment_disbursed` | Staff member's share has been disbursed |
| `review_received` | Staff member received a new review |
| `review_pending` | Supervisor must submit reviews for their team (fires on job completion) |
| `general` | Admin-generated announcements |

#### Sample notification object

```json
{
  "id": 7,
  "notification_type": "application_approved",
  "type_display": "Application Approved",
  "title": "You're in! — 3-Bedroom Move — Westlands to Karen",
  "body": "You have been selected for '3-Bedroom Move...' on 2026-05-20.\nYour team: John Mwangi, Alice Kamau, ...",
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

**`?days=N`** controls the lookback window (default **365**, max 3650). Pass **`?all=true`** to bypass the date filter entirely and return all-time data.

#### Dashboard response shape

```json
{
  "window_days": 365,
  "staff": { "total_active": 15, "available": 12, "on_job": 3 },
  "fleet":  { "total": 6, "available": 4, "on_job": 2, "maintenance": 0 },
  "jobs": {
    "total": 25,
    "pending": 4, "assigned": 2, "in_progress": 1, "completed": 15, "cancelled": 3,
    "unassigned_needing_attention": 2,
    "created_last_365_days": 25
  },
  "billing": {
    "total_invoiced": "520000.00",
    "total_collected": "480000.00",
    "total_outstanding": "40000.00",
    "unpaid_invoices": 3
  },
  "customers": { "total": 42, "new_last_365_days": 42 }
}
```

#### Billing report — `revenue_totals` shape (updated)

```json
{
  "revenue_totals": {
    "total_invoiced": "520000.00",
    "total_collected": "480000.00",
    "total_outstanding": "40000.00",
    "total_company_profit": "430000.00"
  }
}
```

`total_company_profit` is the sum of `invoice.company_profit` across all disbursed invoices in the window — use this to build a profit chart or stat card.

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

# SMTP email — Gmail example (use an App Password, not your account password)
# DEFAULT_FROM_EMAIL must match EMAIL_HOST_USER exactly for Gmail to accept it.
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=youraddress@gmail.com
EMAIL_HOST_PASSWORD=xxxxxxxxxxxxxxxx
DEFAULT_FROM_EMAIL=youraddress@gmail.com
```

> **Important:** `DEFAULT_FROM_EMAIL` must be the same Gmail address as `EMAIL_HOST_USER`. Gmail rejects messages where the sender does not match the authenticated account.

#### Gmail App Password setup

Standard Gmail passwords are blocked for third-party SMTP. Generate an **App Password**:

1. `myaccount.google.com` → **Security** → enable **2-Step Verification**
2. Search **"App passwords"** → App: **Mail** · Device: **Other** → name it `E-Movers`
3. Google shows the password as `xxxx xxxx xxxx xxxx` (spaces for readability)
4. **Remove the spaces** before pasting into `.env` — use `xxxxxxxxxxxxxxxx` (16 characters, no separators)

For other providers (SendGrid, Mailgun, Zoho): same env vars — just change `EMAIL_HOST` and use the provider's SMTP credentials.

---

## 14. Frontend Integration Guide

This section covers everything a frontend developer needs to consume the E-Movers API — token management, request setup, role-based routing, and per-screen API call maps.

---

### 14.1 Base URL

```
Development:  http://localhost:8000/api/v1
Production:   https://e-movers-backend.onrender.com/api/v1
```

Store this in an environment variable (e.g. `VITE_API_BASE_URL` or `NEXT_PUBLIC_API_URL`) and never hard-code it.

---

### 14.2 Authentication Flow

#### Step 1 — Login

```
POST /api/v1/auth/login/
Body: { "email": "...", "password": "..." }
```

On success (`200`), you receive:

```json
{
  "user": { "id": 1, "email": "...", "role": "mover-admin", ... },
  "tokens": { "access": "<jwt>", "refresh": "<jwt>" }
}
```

Store both tokens and the user object:

```js
// Suggested storage
localStorage.setItem('access_token',  data.tokens.access)
localStorage.setItem('refresh_token', data.tokens.refresh)
localStorage.setItem('user',          JSON.stringify(data.user))
```

#### Step 2 — Attach token to every request

Every protected request needs the header:

```
Authorization: Bearer <access_token>
```

#### Step 3 — Refresh the access token

The access token expires after **60 minutes**. When any request returns `401`, use the refresh token to get a new one:

```
POST /api/v1/auth/token/refresh/
Body: { "refresh": "<refresh_token>" }
```

Response:

```json
{ "access": "<new_access_token>", "refresh": "<new_refresh_token>" }
```

Update both stored tokens. The old refresh token is blacklisted automatically.

#### Step 4 — Logout

```
POST /api/v1/auth/logout/
Body: { "refresh": "<refresh_token>" }
```

Then clear storage and redirect to login:

```js
localStorage.removeItem('access_token')
localStorage.removeItem('refresh_token')
localStorage.removeItem('user')
```

---

### 14.3 Axios Setup (Recommended)

```js
// src/lib/api.js
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL, // e.g. http://localhost:8000/api/v1
})

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh on 401
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)))
  failedQueue = []
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => { original.headers.Authorization = `Bearer ${token}`; return api(original) })
          .catch((err) => Promise.reject(err))
      }

      original._retry = true
      isRefreshing = true

      try {
        const refresh = localStorage.getItem('refresh_token')
        const { data } = await axios.post(`${import.meta.env.VITE_API_BASE_URL}/auth/token/refresh/`, { refresh })
        localStorage.setItem('access_token', data.access)
        localStorage.setItem('refresh_token', data.refresh)
        api.defaults.headers.common.Authorization = `Bearer ${data.access}`
        processQueue(null, data.access)
        original.headers.Authorization = `Bearer ${data.access}`
        return api(original)
      } catch (err) {
        processQueue(err, null)
        // Refresh failed — force logout
        localStorage.clear()
        window.location.href = '/login'
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

export default api
```

---

### 14.4 User Roles & Route Protection

There are two roles. Every token payload contains the `role` field. Read it from the stored user object:

```js
const user = JSON.parse(localStorage.getItem('user'))
const isAdmin = user?.role === 'mover-admin'
const isStaff = user?.role === 'mover-staff'
```

#### Role capabilities summary

| Capability | `mover-admin` | `mover-staff` |
|---|:---:|:---:|
| Create / edit jobs | Yes | No |
| View job list | Yes | Yes |
| Apply for jobs | No | Yes |
| View own applications | No | Yes |
| Approve applications | Yes | No |
| Auto-allocate | Yes | No |
| Mark staff absent | Yes | No |
| Start / complete job | Yes | Yes (supervisor only) |
| Generate & view invoices | Yes | Yes (read) |
| Record payments | Yes | No |
| Disburse payments | Yes | No |
| Submit reviews | No | Yes (supervisor only) |
| View review summary | Yes | Yes (own only) |
| View reports / dashboard | Yes | No |
| Register new users | Yes | No |

#### Route guard example (React Router v6)

```jsx
// src/components/RequireRole.jsx
import { Navigate } from 'react-router-dom'

export default function RequireRole({ role, children }) {
  const user = JSON.parse(localStorage.getItem('user'))
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to="/unauthorized" replace />
  return children
}

// Usage in router
<Route path="/reports" element={
  <RequireRole role="mover-admin"><ReportsPage /></RequireRole>
} />
<Route path="/my-applications" element={
  <RequireRole role="mover-staff"><MyApplicationsPage /></RequireRole>
} />
```

---

### 14.5 Suggested Page Structure

```
/login                      → Public
/dashboard                  → Admin only
/jobs                       → Admin + Staff
/jobs/:id                   → Admin + Staff
/jobs/new                   → Admin only
/customers                  → Admin + Staff
/customers/new              → Admin only
/fleet                      → Admin + Staff
/fleet/new                  → Admin only
/staff                      → Admin only
/staff/:id                  → Admin only
/my-applications            → Staff only
/attendance/:jobId          → Admin + Staff
/billing/invoices           → Admin + Staff
/billing/invoices/:id       → Admin + Staff
/reviews/job/:jobId         → Staff (supervisor) + Admin
/notifications              → Admin + Staff
/reports                    → Admin only
/profile                    → Admin + Staff
```

---

### 14.6 Screen-by-Screen API Call Map

#### Login Page

| Action | API Call |
|---|---|
| Submit login form | `POST /auth/login/` |

Store `tokens.access`, `tokens.refresh`, and `user` from the response. Redirect based on `user.role`:
- `mover-admin` → `/dashboard`
- `mover-staff` → `/jobs`

---

#### Admin Dashboard (`/dashboard`)

| Widget | API Call |
|---|---|
| KPI cards | `GET /reports/dashboard/` |
| Jobs needing attention | Use `jobs.unassigned_needing_attention` from dashboard response |
| Recent jobs | `GET /jobs/?ordering=-created_at&page_size=5` |

---

#### Jobs List (`/jobs`)

| Action | API Call |
|---|---|
| Load jobs | `GET /jobs/` |
| Filter by status | `GET /jobs/?status=pending` |
| Search | `GET /jobs/?search=Karen` |
| Filter by date range | `GET /jobs/?scheduled_date_after=2026-05-01&scheduled_date_before=2026-05-31` |
| Unassigned jobs alert | `GET /jobs/unassigned/` |

Pagination: responses include `count`, `next`, `previous`, `results`.

---

#### Job Detail (`/jobs/:id`)

| Action | API Call | Who |
|---|---|---|
| Load job | `GET /jobs/:id/` | Both |
| View applicants | `GET /jobs/:id/applications/` | Admin |
| Approve applicants | `POST /jobs/:id/approve-applications/` | Admin |
| Auto-allocate | `POST /jobs/:id/auto-allocate/` | Admin |
| Change team leader | `PATCH /jobs/:id/change-supervisor/ {"staff_id": N}` | Admin |
| Assign staff manually | `POST /jobs/:id/assign-staff/` | Admin |
| Assign trucks manually | `POST /jobs/:id/assign-trucks/` | Admin |
| Start job | `POST /jobs/:id/status/ {"action":"start"}` | Admin + Supervisor |
| Complete job | `POST /jobs/:id/status/ {"action":"complete"}` | Admin + Supervisor |
| Cancel job | `POST /jobs/:id/status/ {"action":"cancel"}` | Admin |
| Submit team reviews (after completion) | `POST /reviews/bulk-create/` | Supervisor |
| Download team PDF | `GET /jobs/:id/team-pdf/` | Both |
| View attendance | `GET /attendance/:id/` | Both |
| View invoice | `GET /billing/invoices/?job=:id` | Both |

---

#### Staff — Browse & Apply for Jobs

| Action | API Call |
|---|---|
| Browse pending jobs (no login) | `GET /jobs/public/` |
| Apply for a job (authenticated) | `POST /jobs/:id/apply/` |
| Withdraw application | `DELETE /jobs/:id/apply/` |
| My application history | `GET /jobs/my-applications/` |

---

#### Customers (`/customers`)

| Action | API Call |
|---|---|
| List | `GET /customers/` |
| Create | `POST /customers/` |
| Edit | `PATCH /customers/:id/` |
| Delete | `DELETE /customers/:id/` |

---

#### Fleet (`/fleet`)

| Action | API Call |
|---|---|
| List all trucks | `GET /fleet/` |
| Available trucks only | `GET /fleet/available/` |
| Create truck | `POST /fleet/` |
| Edit truck | `PATCH /fleet/:id/` |
| Delete truck | `DELETE /fleet/:id/` |

---

#### Staff List (`/staff`) — Admin only

| Action | API Call |
|---|---|
| List all staff | `GET /users/?role=mover-staff` |
| Available staff | `GET /users/available-staff/` |
| View staff profile | `GET /users/:id/staff-profile/` |
| Update availability/notes | `PATCH /users/:id/staff-profile/ {"is_available": true, "notes": "..."}` |
| Deactivate staff | `DELETE /users/:id/` |
| Register new staff | `POST /auth/register/` |

> **Note:** `average_rating`, `recommendation_score`, and `total_reviews` are **no longer in the API response**. Do not display rating stars or score bars on staff management screens.

---

#### Homepage — Get a Quote (public, no login)

| Action | API Call |
|---|---|
| Download full price guide PDF | `GET /billing/quote/` |

No body, no login. Returns `application/pdf` — wire the button directly to this URL or use `fetch` to trigger a download (see the What Changed section above for both patterns).

---

#### Billing — Invoices (`/billing/invoices`)

| Action | API Call |
|---|---|
| List invoices | `GET /billing/invoices/` |
| Generate invoice for a job | `POST /billing/invoices/generate/` |
| View invoice detail | `GET /billing/invoices/:id/` |
| Record payment | `POST /billing/invoices/:id/pay/` |
| Disburse to staff (KES 500 each) | `POST /billing/invoices/:id/disburse/` |

---

#### Reviews (`/reviews/job/:jobId`) — Supervisor only

| Action | API Call |
|---|---|
| Submit all reviews in one shot | `POST /reviews/bulk-create/` |
| View reviews for a job | `GET /reviews/job/:jobId/` |
| Staff view own reviews | `GET /reviews/my-reviews/` |
| Staff performance summary | `GET /reviews/staff/:id/summary/` |

---

#### Notifications

| Action | API Call |
|---|---|
| Load inbox | `GET /notifications/` |
| Unread badge count | `GET /notifications/unread-count/` |
| Mark one as read | `PATCH /notifications/:id/read/` |
| Mark all as read | `POST /notifications/mark-all-read/` |

Poll or refresh `/notifications/unread-count/` on page focus to keep the badge up to date.

---

#### Reports (`/reports`) — Admin only

| Report | API Call |
|---|---|
| Dashboard KPIs | `GET /reports/dashboard/` |
| Job analytics | `GET /reports/jobs/?days=30` |
| Billing & revenue | `GET /reports/billing/?days=30` |
| Staff performance ranking | `GET /reports/staff-performance/` |
| Fleet utilisation | `GET /reports/fleet/` |
| Attendance rates | `GET /reports/attendance/?days=30` |
| Application volume | `GET /reports/applications/?days=30` |

---

#### Profile (`/profile`)

| Action | API Call |
|---|---|
| Load own profile | `GET /auth/me/` |
| Update name / phone | `PATCH /auth/me/` |
| Change password | `POST /auth/change-password/` with `{ old_password, new_password }` |

---

### 14.7 Error Handling

All API errors return either:

```json
{ "error": "Human-readable message." }
```

or DRF field-level validation errors:

```json
{ "field_name": ["This field is required."] }
```

Recommended centralised error handler:

```js
// src/lib/handleApiError.js
export function getErrorMessage(err) {
  const data = err.response?.data
  if (!data) return 'Network error. Please try again.'
  if (typeof data === 'string') return data
  if (data.error) return data.error
  if (data.detail) return data.detail
  // Field-level errors — join all messages
  return Object.values(data).flat().join(' ')
}
```

#### Common HTTP status codes

| Status | Meaning | Frontend action |
|---|---|---|
| `200` / `201` | Success | Show success state / navigate |
| `400` | Validation or business rule error | Show `error` or field messages |
| `401` | Token expired or missing | Interceptor auto-refreshes; if refresh fails → redirect to `/login` |
| `403` | Wrong role | Show "Access denied" or hide the UI element |
| `404` | Resource not found | Show not-found state |
| `207` | Bulk operation partial success | Show per-item results from `created` and `errors` arrays |

---

### 14.8 Pagination

List endpoints return paginated results:

```json
{
  "count": 47,
  "next": "http://localhost:8000/api/v1/jobs/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Use the `next` / `previous` URLs directly, or append `?page=N` manually. Default page size is 20.

---

### 14.9 Dev Credentials (Seed Data)

Run `python manage.py seed_data` on the backend, then use:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@emovers.co.ke` | `Admin1234!` |
| Staff (any of 20) | `staff01@emovers.co.ke` … `staff20@emovers.co.ke` | `Staff1234!` |
