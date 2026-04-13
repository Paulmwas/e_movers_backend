"""
attendance/services.py
======================
Business logic for attendance confirmation and marking absent.
"""

import random
import string

from django.db import transaction

from jobs.models import Job, JobAssignment
from .models import AttendanceRecord


class AttendanceError(Exception):
    """Raised when an attendance business rule is violated."""
    pass


def generate_attendance_pin(job: Job) -> str:
    """
    Generate a secure 6-digit PIN for a job and persist it on the Job model.

    Parameters
    ----------
    job : Job
        Must be ASSIGNED or IN_PROGRESS.

    Returns
    -------
    str
        The new 6-digit PIN.

    Raises
    ------
    AttendanceError
        If the job is not in a state that allows attendance (not ASSIGNED/IN_PROGRESS).
    """
    if job.status not in (Job.Status.ASSIGNED, Job.Status.IN_PROGRESS):
        raise AttendanceError(
            f"Cannot generate a PIN for a job with status "
            f"'{job.get_status_display()}'. "
            f"Job must be ASSIGNED or IN_PROGRESS."
        )

    pin = "".join(random.choices(string.digits, k=6))
    job.attendance_pin = pin
    job.save(update_fields=["attendance_pin", "updated_at"])
    return pin


@transaction.atomic
def confirm_attendance(job: Job, staff, token: str) -> AttendanceRecord:
    """
    Validate the attendance PIN and create a CONFIRMED attendance record.

    Parameters
    ----------
    job : Job
    staff : User
    token : str
        The 6-digit PIN submitted by the staff member.

    Returns
    -------
    AttendanceRecord

    Raises
    ------
    AttendanceError
        On any business-rule violation.
    """
    if job.status not in (Job.Status.ASSIGNED, Job.Status.IN_PROGRESS):
        raise AttendanceError(
            f"Attendance confirmation is only available for ASSIGNED or "
            f"IN_PROGRESS jobs. This job is '{job.get_status_display()}'."
        )

    if not job.attendance_pin:
        raise AttendanceError(
            "No attendance PIN has been generated for this job yet. "
            "Please ask your admin to generate one."
        )

    if job.attendance_pin != token:
        raise AttendanceError("Invalid PIN. Please check with your admin.")

    is_assigned = JobAssignment.objects.filter(job=job, staff=staff).exists()
    if not is_assigned:
        raise AttendanceError("You are not assigned to this job.")

    if AttendanceRecord.objects.filter(job=job, staff=staff).exists():
        raise AttendanceError("Your attendance has already been recorded for this job.")

    return AttendanceRecord.objects.create(
        job=job,
        staff=staff,
        status=AttendanceRecord.Status.CONFIRMED,
        confirmed_by=staff,
        confirmation_token=token,
    )


@transaction.atomic
def mark_absent(job: Job, staff_id: int, recorded_by) -> AttendanceRecord:
    """
    Admin marks a staff member as absent for a job.

    Parameters
    ----------
    job : Job
    staff_id : int
    recorded_by : User
        The admin recording the absence.

    Returns
    -------
    AttendanceRecord

    Raises
    ------
    AttendanceError
        When staff is not assigned, or attendance is already recorded.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        staff = User.objects.get(pk=staff_id)
    except User.DoesNotExist:
        raise AttendanceError(f"Staff member with ID {staff_id} does not exist.")

    is_assigned = JobAssignment.objects.filter(job=job, staff=staff).exists()
    if not is_assigned:
        raise AttendanceError(
            f"{staff.get_full_name()} is not assigned to this job."
        )

    record, created = AttendanceRecord.objects.get_or_create(
        job=job,
        staff=staff,
        defaults={
            "status": AttendanceRecord.Status.ABSENT,
            "confirmed_by": recorded_by,
            "notes": "Marked absent by admin.",
        },
    )

    if not created:
        raise AttendanceError(
            f"Attendance for {staff.get_full_name()} has already been recorded "
            f"as '{record.get_status_display()}'."
        )

    return record
