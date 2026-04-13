"""
attendance/models.py
====================
Tracks whether each assigned staff member confirmed their presence
on the morning of the moving day.

Confirmation algorithm (PIN-based):
  1. Admin generates a 6-digit PIN for the job on the morning of the move.
     The PIN is stored on jobs.Job.attendance_pin.
  2. Each staff member submits POST /api/v1/attendance/confirm/ with the PIN.
  3. The system validates the PIN, checks assignment, and creates an
     AttendanceRecord(status=CONFIRMED).
  4. Admin can manually mark absent staff via POST /api/v1/attendance/<job_id>/mark-absent/.
"""

from django.db import models
from django.conf import settings


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        ABSENT = "absent", "Absent"

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    confirmed_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_attendance",
        help_text="Same as staff for self-confirmation; admin user for absent records.",
    )
    confirmation_token = models.CharField(
        max_length=64,
        blank=True,
        help_text="The PIN submitted by the staff member at confirmation time.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("job", "staff")]
        ordering = ["-confirmed_at"]
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"

    def __str__(self):
        return (
            f"{self.staff.get_full_name()} — {self.job.title} [{self.status.upper()}]"
        )
