"""
jobs/services.py
================
All business logic for job operations lives here — views stay thin.

Key services:
  - auto_allocate_job    : Fully automatic staff + truck assignment
  - assign_staff_to_job  : Manual staff assignment
  - assign_trucks_to_job : Manual truck assignment
  - transition_job_status: Enforces the status state machine
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import User, StaffProfile
from fleet.models import Truck
from .models import Job, JobAssignment, JobTruck, JobApplication


class AllocationError(Exception):
    """Raised when auto-allocation cannot satisfy requirements."""
    pass


class StatusTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""
    pass


class ApplicationError(Exception):
    """Raised when a job application business rule is violated."""
    pass


# ---------------------------------------------------------------------------
# Auto-allocation
# ---------------------------------------------------------------------------

@transaction.atomic
def auto_allocate_job(job: Job, requested_by: User, num_movers: int = 10, num_trucks: int = 1):
    """
    Fully automatic allocation of staff and trucks to a job.

    Algorithm:
      1. Clear any existing assignments for this job (idempotent re-run).
      2. Fetch all active staff who are currently available,
         ordered by recommendation_score DESC (best candidates first).
         Minimum recommendation_score ensures even low-rated staff
         still appear in the pool when no one better is available.
      3. The first staff member in the sorted list becomes the SUPERVISOR.
      4. The next `num_movers` staff become MOVERs.
      5. Fetch `num_trucks` available trucks ordered by capacity DESC.
      6. Lock staff as unavailable, lock trucks as on_job.
      7. Transition job to ASSIGNED status.

    Raises AllocationError if there are not enough staff or trucks available.
    """
    if job.status not in (Job.Status.PENDING, Job.Status.ASSIGNED):
        raise AllocationError(
            f"Cannot allocate a job with status '{job.get_status_display()}'. "
            "Only PENDING or ASSIGNED jobs can be re-allocated."
        )

    # --- Staff pool: active staff ordered by recommendation score ---
    total_staff_needed = num_movers + 1  # +1 for supervisor

    available_staff = list(
        User.objects.filter(
            role=User.Role.STAFF,
            is_active=True,
            staff_profile__is_available=True,
        )
        .select_related("staff_profile")
        .order_by("-staff_profile__recommendation_score")[:total_staff_needed]
    )

    if len(available_staff) < total_staff_needed:
        raise AllocationError(
            f"Not enough available staff. "
            f"Need {total_staff_needed} (1 supervisor + {num_movers} movers), "
            f"found {len(available_staff)} available."
        )

    # --- Truck pool ---
    available_trucks = list(
        Truck.objects.filter(status=Truck.Status.AVAILABLE)
        .order_by("-capacity_tons")[:num_trucks]
    )

    if len(available_trucks) < num_trucks:
        raise AllocationError(
            f"Not enough available trucks. "
            f"Need {num_trucks}, found {len(available_trucks)} available."
        )

    # --- Clear existing assignments (re-run safety) ---
    _release_existing_assignments(job)

    # --- Create assignments ---
    supervisor_user = available_staff[0]
    movers = available_staff[1:]

    JobAssignment.objects.create(
        job=job,
        staff=supervisor_user,
        role=JobAssignment.Role.SUPERVISOR,
        assigned_by=requested_by,
    )
    JobAssignment.objects.bulk_create([
        JobAssignment(
            job=job,
            staff=mover,
            role=JobAssignment.Role.MOVER,
            assigned_by=requested_by,
        )
        for mover in movers
    ])

    # --- Create truck assignments ---
    JobTruck.objects.bulk_create([
        JobTruck(job=job, truck=truck, assigned_by=requested_by)
        for truck in available_trucks
    ])

    # --- Lock resources ---
    User.objects.filter(pk__in=[s.pk for s in available_staff]).update()
    StaffProfile.objects.filter(
        user__in=available_staff
    ).update(is_available=False)

    Truck.objects.filter(pk__in=[t.pk for t in available_trucks]).update(
        status=Truck.Status.ON_JOB
    )

    # --- Transition job status ---
    job.status = Job.Status.ASSIGNED
    job.save(update_fields=["status", "updated_at"])

    return job


# ---------------------------------------------------------------------------
# Manual assignment
# ---------------------------------------------------------------------------

@transaction.atomic
def assign_staff_to_job(job: Job, staff_ids: list, requested_by: User):
    """
    Manually assign specific staff members to a job.

    Rules:
      - Job must be PENDING or ASSIGNED.
      - Each staff member must be active and available.
      - If a SUPERVISOR already exists on this job, incoming staff
        get role=MOVER. If there is no supervisor yet, the first
        staff in the list becomes SUPERVISOR.
      - Duplicate assignments are silently skipped.
    """
    if job.status not in (Job.Status.PENDING, Job.Status.ASSIGNED):
        raise AllocationError(
            f"Cannot assign staff to a job with status '{job.get_status_display()}'."
        )

    staff_members = User.objects.filter(
        pk__in=staff_ids,
        role=User.Role.STAFF,
        is_active=True,
        staff_profile__is_available=True,
    ).select_related("staff_profile")

    found_ids = set(staff_members.values_list("pk", flat=True))
    missing = set(staff_ids) - found_ids
    if missing:
        raise AllocationError(
            f"Staff IDs {sorted(missing)} are unavailable or do not exist."
        )

    has_supervisor = job.assignments.filter(role=JobAssignment.Role.SUPERVISOR).exists()
    existing_staff_ids = set(job.assignments.values_list("staff_id", flat=True))
    new_assignments = []
    newly_assigned_staff = []

    for i, staff in enumerate(staff_members):
        if staff.pk in existing_staff_ids:
            continue

        role = JobAssignment.Role.MOVER
        if not has_supervisor and i == 0:
            role = JobAssignment.Role.SUPERVISOR
            has_supervisor = True

        new_assignments.append(
            JobAssignment(job=job, staff=staff, role=role, assigned_by=requested_by)
        )
        newly_assigned_staff.append(staff)

    JobAssignment.objects.bulk_create(new_assignments)

    # Lock availability for newly assigned staff
    StaffProfile.objects.filter(
        user__in=newly_assigned_staff
    ).update(is_available=False)

    # Transition to ASSIGNED if job was PENDING
    if job.status == Job.Status.PENDING:
        job.status = Job.Status.ASSIGNED
        job.save(update_fields=["status", "updated_at"])

    return job


@transaction.atomic
def assign_trucks_to_job(job: Job, truck_ids: list, requested_by: User):
    """
    Manually assign specific trucks to a job.
    Trucks must be AVAILABLE. Duplicate assignments are silently skipped.
    """
    if job.status not in (Job.Status.PENDING, Job.Status.ASSIGNED):
        raise AllocationError(
            f"Cannot assign trucks to a job with status '{job.get_status_display()}'."
        )

    trucks = Truck.objects.filter(
        pk__in=truck_ids,
        status=Truck.Status.AVAILABLE,
    )

    found_ids = set(trucks.values_list("pk", flat=True))
    missing = set(truck_ids) - found_ids
    if missing:
        raise AllocationError(
            f"Truck IDs {sorted(missing)} are unavailable or do not exist."
        )

    existing_truck_ids = set(job.job_trucks.values_list("truck_id", flat=True))
    new_job_trucks = []
    newly_assigned_trucks = []

    for truck in trucks:
        if truck.pk in existing_truck_ids:
            continue
        new_job_trucks.append(
            JobTruck(job=job, truck=truck, assigned_by=requested_by)
        )
        newly_assigned_trucks.append(truck)

    JobTruck.objects.bulk_create(new_job_trucks)

    Truck.objects.filter(
        pk__in=[t.pk for t in newly_assigned_trucks]
    ).update(status=Truck.Status.ON_JOB)

    return job


# ---------------------------------------------------------------------------
# Status machine
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    Job.Status.PENDING: [Job.Status.ASSIGNED, Job.Status.CANCELLED],
    Job.Status.ASSIGNED: [Job.Status.IN_PROGRESS, Job.Status.CANCELLED],
    Job.Status.IN_PROGRESS: [Job.Status.COMPLETED, Job.Status.CANCELLED],
    Job.Status.COMPLETED: [],
    Job.Status.CANCELLED: [],
}


@transaction.atomic
def transition_job_status(job: Job, new_status: str, requested_by: User):
    """
    Enforce the job status state machine.

    Transitions:
      pending     -> assigned      (requires at least 1 staff + 1 truck)
      pending     -> cancelled
      assigned    -> in_progress   (requires at least 1 supervisor on the job)
      assigned    -> cancelled
      in_progress -> completed     (records completed_at timestamp)
      in_progress -> cancelled
      completed   -> (terminal, no transition)
      cancelled   -> (terminal, no transition)

    On COMPLETED:  releases staff and trucks back to available.
    On CANCELLED:  releases staff and trucks back to available.
    """
    allowed = VALID_TRANSITIONS.get(job.status, [])
    if new_status not in allowed:
        raise StatusTransitionError(
            f"Cannot transition from '{job.get_status_display()}' to "
            f"'{dict(Job.Status.choices).get(new_status, new_status)}'. "
            f"Allowed transitions: {[dict(Job.Status.choices).get(s, s) for s in allowed] or 'None'}."
        )

    # Gate: moving to IN_PROGRESS requires a supervisor
    if new_status == Job.Status.IN_PROGRESS:
        if not job.assignments.filter(role=JobAssignment.Role.SUPERVISOR).exists():
            raise StatusTransitionError(
                "Cannot start a job without a supervisor assigned."
            )
        job.started_at = timezone.now()

    # Gate: moving to ASSIGNED requires at least 1 staff + 1 truck
    if new_status == Job.Status.ASSIGNED:
        if not job.assignments.exists():
            raise StatusTransitionError(
                "Cannot mark job as Assigned without any staff assignment."
            )
        if not job.job_trucks.exists():
            raise StatusTransitionError(
                "Cannot mark job as Assigned without any truck assignment."
            )

    # On terminal states, release all resources
    if new_status in (Job.Status.COMPLETED, Job.Status.CANCELLED):
        if new_status == Job.Status.COMPLETED:
            job.completed_at = timezone.now()
        _release_job_resources(job)

    job.status = new_status
    job.save(update_fields=["status", "started_at", "completed_at", "updated_at"])
    return job


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _release_existing_assignments(job: Job):
    """
    Free up staff and trucks from an existing assignment set before re-allocating.
    Called at the start of auto_allocate_job to make it idempotent.
    """
    staff_ids = list(job.assignments.values_list("staff_id", flat=True))
    truck_ids = list(job.job_trucks.values_list("truck_id", flat=True))

    job.assignments.all().delete()
    job.job_trucks.all().delete()

    if staff_ids:
        StaffProfile.objects.filter(user_id__in=staff_ids).update(is_available=True)

    if truck_ids:
        Truck.objects.filter(pk__in=truck_ids).update(status=Truck.Status.AVAILABLE)


def _release_job_resources(job: Job):
    """
    Release all staff and trucks tied to a job back to available.
    Called when a job is COMPLETED or CANCELLED.
    """
    staff_ids = list(job.assignments.values_list("staff_id", flat=True))
    truck_ids = list(job.job_trucks.values_list("truck_id", flat=True))

    if staff_ids:
        StaffProfile.objects.filter(user_id__in=staff_ids).update(is_available=True)

    if truck_ids:
        Truck.objects.filter(pk__in=truck_ids).update(status=Truck.Status.AVAILABLE)


# ---------------------------------------------------------------------------
# Job Application Flow
# ---------------------------------------------------------------------------

@transaction.atomic
def apply_for_job(job: Job, staff: User) -> JobApplication:
    """
    Submit a new application for an open job.

    Parameters
    ----------
    job : Job
        The job to apply for.
    staff : User
        The mover-staff user applying.

    Returns
    -------
    JobApplication

    Raises
    ------
    ApplicationError
        When any business rule is violated.
    """
    if job.status != Job.Status.PENDING:
        raise ApplicationError("Applications are only open for PENDING jobs.")

    if job.application_deadline and timezone.now() > job.application_deadline:
        raise ApplicationError("The application deadline for this job has passed.")

    active_count = job.applications.filter(
        status=JobApplication.Status.APPLIED
    ).count()
    if active_count >= job.max_applicants:
        raise ApplicationError(
            "This job has reached its maximum number of applicants."
        )

    if job.applications.filter(staff=staff).exclude(
        status=JobApplication.Status.WITHDRAWN
    ).exists():
        raise ApplicationError("You have already applied for this job.")

    if not staff.is_active:
        raise ApplicationError("Your account is deactivated.")

    return JobApplication.objects.create(job=job, staff=staff)


@transaction.atomic
def withdraw_application(job: Job, staff: User) -> JobApplication:
    """
    Staff withdraws their own APPLIED application.

    Parameters
    ----------
    job : Job
    staff : User

    Returns
    -------
    JobApplication

    Raises
    ------
    ApplicationError
        When the application is not found or is not in APPLIED status.
    """
    try:
        application = JobApplication.objects.get(
            job=job, staff=staff, status=JobApplication.Status.APPLIED
        )
    except JobApplication.DoesNotExist:
        raise ApplicationError(
            "No active application found. You may not have applied, or the "
            "application was already processed."
        )

    application.status = JobApplication.Status.WITHDRAWN
    application.save(update_fields=["status"])
    return application


@transaction.atomic
def approve_applications(
    job: Job,
    approved_staff_ids: list,
    supervisor_id: int,
    reviewed_by: User,
) -> Job:
    """
    Admin approves a subset of applicants, designates one as supervisor,
    auto-rejects the rest, creates JobAssignments, and transitions job to ASSIGNED.

    Parameters
    ----------
    job : Job
        Must be PENDING.
    approved_staff_ids : list[int]
        User PKs of the staff to approve (must all have APPLIED status).
    supervisor_id : int
        User PK of the chosen supervisor — must be in approved_staff_ids.
    reviewed_by : User
        The admin performing the approval.

    Returns
    -------
    Job
        The updated job (status=ASSIGNED).

    Raises
    ------
    ApplicationError
        On any business-rule violation.
    """
    if job.status != Job.Status.PENDING:
        raise ApplicationError(
            f"Can only approve applications for PENDING jobs. "
            f"This job is '{job.get_status_display()}'."
        )

    if not approved_staff_ids:
        raise ApplicationError("You must approve at least one staff member.")

    if supervisor_id not in approved_staff_ids:
        raise ApplicationError(
            "The supervisor must be included in the approved staff list."
        )

    # Fetch matching APPLIED applications
    applications = JobApplication.objects.filter(
        job=job,
        staff_id__in=approved_staff_ids,
        status=JobApplication.Status.APPLIED,
    ).select_related("staff")

    found_ids = set(applications.values_list("staff_id", flat=True))
    missing = set(approved_staff_ids) - found_ids
    if missing:
        raise ApplicationError(
            f"Staff IDs {sorted(missing)} do not have an APPLIED application "
            f"for this job."
        )

    now = timezone.now()

    # Approve selected staff and create assignments
    for app in applications:
        app.status = JobApplication.Status.APPROVED
        app.reviewed_by = reviewed_by
        app.reviewed_at = now
        app.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        role = (
            JobAssignment.Role.SUPERVISOR
            if app.staff_id == supervisor_id
            else JobAssignment.Role.MOVER
        )
        JobAssignment.objects.get_or_create(
            job=job,
            staff=app.staff,
            defaults={"role": role, "assigned_by": reviewed_by},
        )

    # Auto-reject remaining APPLIED applications
    remaining_qs = job.applications.filter(status=JobApplication.Status.APPLIED)
    rejected_staff_ids = list(remaining_qs.values_list("staff_id", flat=True))
    remaining_qs.update(
        status=JobApplication.Status.REJECTED,
        reviewed_by=reviewed_by,
        reviewed_at=now,
    )

    # Lock approved staff as unavailable
    StaffProfile.objects.filter(user_id__in=approved_staff_ids).update(
        is_available=False
    )

    # Transition job to ASSIGNED
    job.status = Job.Status.ASSIGNED
    job.save(update_fields=["status", "updated_at"])

    # Fire signal → notifications sent in jobs/signals.py
    from jobs.signals import applications_approved as applications_approved_signal
    applications_approved_signal.send(
        sender=job.__class__,
        job=job,
        approved_staff_ids=list(approved_staff_ids),
        rejected_staff_ids=rejected_staff_ids,
    )

    return job
