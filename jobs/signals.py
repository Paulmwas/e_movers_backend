"""
jobs/signals.py
===============
Custom signals fired during the job lifecycle.

Signal: applications_approved
  Fired by approve_applications() after assignments are created and
  the job transitions to ASSIGNED. Triggers notifications to both
  approved and rejected applicants.

Signal: job_completed
  Fired by transition_job_status() when a job transitions to COMPLETED.
  Sends the supervisor a review_pending notification listing their team.
"""

from django.dispatch import Signal, receiver
from django.contrib.auth import get_user_model

from .models import JobAssignment

applications_approved = Signal()
job_completed = Signal()

User = get_user_model()


@receiver(applications_approved)
def send_approval_notifications(
    sender, job, approved_staff_ids, rejected_staff_ids, **kwargs
):
    """
    Send in-app notifications after admin approves applications.

    Approved staff receive:
      - Approval message with the full team list and scheduled date.

    Rejected staff receive:
      - A polite rejection notice.
    """
    from notifications.services import notify_many

    approved_users = list(User.objects.filter(pk__in=approved_staff_ids))
    team_names = ", ".join(u.get_full_name() for u in approved_users)

    team_body = (
        f"You have been selected for '{job.title}' on {job.scheduled_date}.\n"
        f"Your team: {team_names}."
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


@receiver(job_completed)
def send_review_pending_notification(sender, job, **kwargs):
    """
    Notify the supervisor that the job is done and reviews are due.

    Fired when a job transitions to COMPLETED. The supervisor receives
    a review_pending notification listing the movers they must rate.
    """
    from notifications.services import notify

    supervisor = job.supervisor
    if supervisor is None:
        return

    mover_names = ", ".join(
        a.staff.get_full_name()
        for a in job.assignments
        .filter(role=JobAssignment.Role.MOVER)
        .select_related("staff")
        .order_by("staff__first_name")
    )

    notify(
        recipient=supervisor,
        notification_type="review_pending",
        title=f"Please review your team — {job.title}",
        body=(
            f"The job '{job.title}' has been completed. "
            f"Please submit your performance reviews for the following team members: "
            f"{mover_names}."
        ),
        job=job,
    )
