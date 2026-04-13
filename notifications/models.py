"""
notifications/models.py
=======================
In-app notification model. Notifications are created programmatically
via notifications/services.py — never directly by views.

Supported notification types:
  application_approved  — Staff member was selected for a job
  application_rejected  — Staff member was not selected
  job_team_announced    — Full team list broadcast (attached to approval)
  attendance_reminder   — Reminder to confirm attendance
  payment_disbursed     — Staff member's payment has been disbursed
  review_received       — Staff received a new review
  general               — Administrative messages
"""

from django.db import models
from django.conf import settings


class Notification(models.Model):
    class Type(models.TextChoices):
        APPLICATION_APPROVED = "application_approved", "Application Approved"
        APPLICATION_REJECTED = "application_rejected", "Application Rejected"
        JOB_TEAM_ANNOUNCED = "job_team_announced", "Job Team Announced"
        ATTENDANCE_REMINDER = "attendance_reminder", "Attendance Reminder"
        PAYMENT_DISBURSED = "payment_disbursed", "Payment Disbursed"
        REVIEW_RECEIVED = "review_received", "Review Received"
        GENERAL = "general", "General"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.GENERAL,
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.recipient.get_full_name()}"
