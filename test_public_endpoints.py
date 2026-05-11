"""
Smoke test for public (no-auth) job endpoints using Django's test client.
Run with: python manage.py shell < test_public_endpoints.py
Or:        python manage.py test --keepdb (if converted to unittest)

Usage (from manage.py shell):
    exec(open('test_public_endpoints.py').read())
"""
import os, sys, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_movers.settings")

import django
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from jobs.models import Job, JobApplication
from customers.models import Customer

User = get_user_model()
client = Client()

PASS = 0
FAIL = 0


def check(label, response, expected_status):
    global PASS, FAIL
    ok = response.status_code == expected_status
    sym = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    try:
        data = response.json()
        detail = data.get("error") or data.get("message") or ""
    except Exception:
        detail = ""
    suffix = f"  -> {detail}" if detail else ""
    print(f"  [{sym}] {label} (HTTP {response.status_code}){suffix}")
    if not ok:
        try:
            print(f"         body: {json.dumps(response.json())[:200]}")
        except Exception:
            pass
    return ok


print("\n--- Public job listing (no auth) ---")
r = client.get("/api/v1/jobs/public/")
check("GET /jobs/public/ returns 200", r, 200)
jobs = r.json().get("results", r.json())
print(f"  {len(jobs)} pending jobs visible to anonymous user")
for j in jobs:
    print(f"  Job {j['id']}: \"{j['title'][:45]}\" | applicants={j['applicant_count']} | open={j['is_open_for_applications']}")

open_job = next((j for j in jobs if j["is_open_for_applications"]), None)

print("\n--- Public apply (no auth) ---")
if open_job:
    jid = open_job["id"]

    # Clean up any leftover application from previous test runs
    client.delete(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "staff20@emovers.co.ke"}),
        content_type="application/json",
    )

    # Valid staff email not yet applied to this job
    r = client.post(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "staff20@emovers.co.ke"}),
        content_type="application/json",
    )
    check(f"Apply with valid staff email -> 201", r, 201)

    # Duplicate apply
    r = client.post(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "staff20@emovers.co.ke"}),
        content_type="application/json",
    )
    check("Duplicate apply returns 400", r, 400)

    # Unknown email
    r = client.post(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "nobody@example.com"}),
        content_type="application/json",
    )
    check("Unknown email returns 404", r, 404)

    # Admin email (role=mover-admin, not staff)
    r = client.post(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "admin@emovers.co.ke"}),
        content_type="application/json",
    )
    check("Admin email (not mover-staff) returns 404", r, 404)

    # Missing email field
    r = client.post(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({}),
        content_type="application/json",
    )
    check("Missing email field returns 400", r, 400)

    print("\n--- Public withdraw (no auth) ---")
    r = client.delete(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "staff20@emovers.co.ke"}),
        content_type="application/json",
    )
    check("Withdraw valid application -> 200", r, 200)

    # Double withdraw
    r = client.delete(
        f"/api/v1/jobs/{jid}/public-apply/",
        data=json.dumps({"email": "staff20@emovers.co.ke"}),
        content_type="application/json",
    )
    check("Double withdraw returns 400", r, 400)
else:
    print("  SKIP — no open pending jobs in seed data")

print("\n--- Admin auth (authenticated endpoints) ---")
login_r = client.post(
    "/api/v1/auth/login/",
    data=json.dumps({"email": "admin@emovers.co.ke", "password": "Admin1234!"}),
    content_type="application/json",
)
check("Admin login returns 200", login_r, 200)
access_token = login_r.json().get("tokens", {}).get("access", "")

admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

print("\n--- Admin: view applications for a job with applications ---")
job_with_apps = next((j for j in jobs if j["applicant_count"] > 0), None)
if job_with_apps:
    jid = job_with_apps["id"]
    r = client.get(f"/api/v1/jobs/{jid}/applications/", **admin_headers)
    check(f"Admin list applications for job {jid}", r, 200)
    apps = r.json().get("results", r.json())
    print(f"  {len(apps)} applicants (ordered by recommendation_score)")
    for a in apps[:3]:
        score = a.get("recommendation_score", "?")
        print(f"    {a['staff_name']} | score={score} | status={a['status']}")

print("\n--- Admin: Job CRUD ---")
# Get a customer ID
r = client.get("/api/v1/customers/", **admin_headers)
customers = r.json().get("results", r.json())
cid = customers[0]["id"] if customers else 1

# Create
r = client.post(
    "/api/v1/jobs/",
    data=json.dumps({
        "title": "CRUD Test — Westlands to Karen",
        "customer": cid,
        "move_size": "studio",
        "pickup_address": "1 Westlands, Nairobi",
        "dropoff_address": "1 Karen Road, Nairobi",
        "estimated_distance_km": "10.00",
        "scheduled_date": "2026-06-15",
        "requested_staff_count": 3,
        "requested_truck_count": 1,
    }),
    content_type="application/json",
    **admin_headers,
)
check("Create job (POST /jobs/)", r, 201)
new_id = r.json().get("id") if r.status_code == 201 else None

if new_id:
    # Read
    r = client.get(f"/api/v1/jobs/{new_id}/", **admin_headers)
    check("Read created job (GET /jobs/<id>/)", r, 200)

    # Update
    r = client.patch(
        f"/api/v1/jobs/{new_id}/",
        data=json.dumps({"notes": "Updated via CRUD test."}),
        content_type="application/json",
        **admin_headers,
    )
    check("Update job (PATCH /jobs/<id>/)", r, 200)

    # Staff cannot delete (should return 403)
    login_s = client.post(
        "/api/v1/auth/login/",
        data=json.dumps({"email": "staff01@emovers.co.ke", "password": "Staff1234!"}),
        content_type="application/json",
    )
    staff_token = login_s.json().get("tokens", {}).get("access", "")
    staff_headers = {"HTTP_AUTHORIZATION": f"Bearer {staff_token}"}
    r = client.delete(f"/api/v1/jobs/{new_id}/", **staff_headers)
    check("Staff cannot delete job (403)", r, 403)

    # Admin deletes
    r = client.delete(f"/api/v1/jobs/{new_id}/", **admin_headers)
    check("Admin deletes job (DELETE /jobs/<id>/)", r, 200)

    # Verify gone
    r = client.get(f"/api/v1/jobs/{new_id}/", **admin_headers)
    check("Deleted job returns 404", r, 404)

print("\n--- Admin: approve applications (staff selected based on review score) ---")
# Use a job that has APPLIED applications — pick the one with most applicants
job_with_most_apps = max(jobs, key=lambda j: j["applicant_count"]) if jobs else None
if job_with_most_apps and job_with_most_apps["applicant_count"] >= 2:
    jid = job_with_most_apps["id"]
    print(f"  Using job {jid}: \"{job_with_most_apps['title'][:40]}\" ({job_with_most_apps['applicant_count']} applicants)")

    # Get the applications sorted by score
    r = client.get(f"/api/v1/jobs/{jid}/applications/?status=applied", **admin_headers)
    apps = r.json().get("results", r.json())
    applied_apps = [a for a in apps if a["status"] == "applied"]
    print(f"  {len(applied_apps)} APPLIED applicants (ranked by recommendation_score):")
    for a in applied_apps[:5]:
        print(f"    {a['staff_name']} | score={a['recommendation_score']} | avg_rating={a['average_rating']}")

    if len(applied_apps) >= 2:
        # Approve top 2 applicants; first one becomes supervisor
        approved_ids = [a["staff"] for a in applied_apps[:2]]
        supervisor_id = approved_ids[0]

        # First assign a truck (needed for job to go ASSIGNED)
        truck_r = client.get("/api/v1/fleet/available/", **admin_headers)
        trucks = truck_r.json().get("results", truck_r.json())
        if trucks:
            client.post(
                f"/api/v1/jobs/{jid}/assign-trucks/",
                data=json.dumps({"truck_ids": [trucks[0]["id"]]}),
                content_type="application/json",
                **admin_headers,
            )

        r = client.post(
            f"/api/v1/jobs/{jid}/approve-applications/",
            data=json.dumps({
                "approved_staff_ids": approved_ids,
                "supervisor_id": supervisor_id,
            }),
            content_type="application/json",
            **admin_headers,
        )
        check(f"Approve top applicants for job {jid}", r, 200)
        if r.status_code == 200:
            job_data = r.json().get("job", {})
            print(f"  Job status is now: {job_data.get('status')}")
            for a in job_data.get("assignments", []):
                print(f"  {a['role'].upper()}: {a['staff_name']} | score={a['recommendation_score']}")
else:
    print("  SKIP — need at least 2 applied applicants for this test")

print("\n" + "=" * 55)
total = PASS + FAIL
print(f"  Results: {PASS}/{total} passed  |  {FAIL} failed")
print("=" * 55)
if FAIL > 0:
    sys.exit(1)
