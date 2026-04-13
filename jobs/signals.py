"""
jobs/signals.py
===============
Custom signals fired during the job application lifecycle.

Signal: applications_approved
  Fired by approve_applications() after assignments are created and
  the job transitions to ASSIGNED. Triggers notifications to both
  approved and rejected applicants.
"""

from django.dispatch import Signal, receiver
from django.contrib.auth import get_user_model

applications_approved = Signal()

User = get_user_model()


@receiver(applications_approved)
def send_approval_notifications(
    sender, job, approved_staff_ids, rejected_staff_ids, **kwargs
):
    """
    Send in-app notifications after admin approves applications.

    Approved staff receive:
      - Approval message with the full team list and date.

    Rejected staff receive:
      - A polite rejection notice.
    """
    # Lazy import to avoid circular dependency at module load time
    from notifications.services import notify_many

    approved_users = list(User.objects.filter(pk__in=approved_staff_ids))
    team_names = ", ".join(u.get_full_name() for u in approved_users)

    team_body = (
        f"You have been selected for '{job.title}' on {job.scheduled_date}.\n"
        f"Your team: {team_names}.\n"
        f"Please confirm your attendance on the morning of the move."
    )

    notify_many(
        recipients=approved_users,
        notification_type="application_approved",
        title=f"You're in! — {job.title}",
        body=team_body,
        job=job,
    )

    if rejected_staff_ids:
        rejected_users = list(User.objects.filter(pk__in=rejected_staff_ids))
        notify_many(
            recipients=rejected_users,
            notification_type="application_rejected",
            title=f"Application Update — {job.title}",
            body=(
                f"Thank you for applying for '{job.title}'. "
                f"Unfortunately you were not selected for this move. "
                f"Keep applying — your next opportunity is coming!"
            ),
            job=job,
        )
