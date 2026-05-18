"""
notifications/services.py
=========================
Helper functions for creating in-app notifications and sending SMTP emails.

All other apps should call notify() / notify_many() — never create
Notification objects or send emails directly.

Email delivery:
  _send_email() is called after each notification is persisted.
  It only fires for notification types that have a registered HTML builder
  (currently: application_approved, payment_disbursed).
  Failures are logged and swallowed — a broken SMTP config never prevents
  the in-app notification from being saved, and never fails a request.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML email builders
# ---------------------------------------------------------------------------

def _build_application_approved_html(recipient, title: str, body: str, job) -> str:
    name = recipient.get_full_name() or recipient.email

    time_row = ""
    if job and job.scheduled_time:
        time_row = f"""
            <tr>
              <td style="padding:5px 0;color:#374151;font-size:14px;">
                <strong>Time:</strong> {job.scheduled_time.strftime('%I:%M %p')}
              </td>
            </tr>"""

    location_rows = ""
    if job:
        location_rows = f"""
            <tr>
              <td style="padding:5px 0;color:#374151;font-size:14px;">
                <strong>Pickup:</strong> {job.pickup_address}
              </td>
            </tr>
            <tr>
              <td style="padding:5px 0;color:#374151;font-size:14px;">
                <strong>Drop-off:</strong> {job.dropoff_address}
              </td>
            </tr>"""

    job_box = ""
    if job:
        job_box = f"""
        <table cellpadding="0" cellspacing="0" border="0"
               style="width:100%;background:#eff6ff;border-left:4px solid #1a56db;
                      border-radius:4px;padding:14px 16px;margin:20px 0;">
          <tr>
            <td style="padding:5px 0;color:#374151;font-size:14px;">
              <strong>Job:</strong> {job.title}
            </td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#374151;font-size:14px;">
              <strong>Date:</strong> {job.scheduled_date.strftime('%A, %d %B %Y')}
            </td>
          </tr>
          {time_row}
          {location_rows}
        </table>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
  <table cellpadding="0" cellspacing="0" border="0"
         style="max-width:600px;margin:32px auto;background:#ffffff;
                border-radius:8px;overflow:hidden;
                box-shadow:0 1px 6px rgba(0,0,0,0.10);">
    <tr>
      <td style="background:#1a56db;padding:24px 32px;">
        <p style="margin:0;color:#ffffff;font-size:20px;font-weight:bold;">E-Movers</p>
        <p style="margin:4px 0 0;color:#bfdbfe;font-size:13px;">Job Assignment Confirmation</p>
      </td>
    </tr>
    <tr>
      <td style="padding:28px 32px;">
        <p style="margin:0 0 12px;font-size:16px;color:#111827;">Hi {name},</p>
        <p style="margin:0 0 4px;font-size:15px;color:#374151;line-height:1.6;">
          Great news — you have been selected for an upcoming move!
        </p>
        {job_box}
        <p style="margin:0 0 16px;font-size:14px;color:#374151;line-height:1.7;white-space:pre-line;">{body}</p>
        <p style="margin:0;font-size:14px;color:#6b7280;">
          Check the app for full job details. If you have questions, contact your team supervisor.
        </p>
      </td>
    </tr>
    <tr>
      <td style="background:#f9fafb;padding:14px 32px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
          Automated message from E-Movers &mdash; please do not reply to this email.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_payment_disbursed_html(recipient, title: str, body: str, job) -> str:
    name = recipient.get_full_name() or recipient.email
    job_name = job.title if job else "your recent job"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
  <table cellpadding="0" cellspacing="0" border="0"
         style="max-width:600px;margin:32px auto;background:#ffffff;
                border-radius:8px;overflow:hidden;
                box-shadow:0 1px 6px rgba(0,0,0,0.10);">
    <tr>
      <td style="background:#057a55;padding:24px 32px;">
        <p style="margin:0;color:#ffffff;font-size:20px;font-weight:bold;">E-Movers</p>
        <p style="margin:4px 0 0;color:#bcf0da;font-size:13px;">Payment Disbursed</p>
      </td>
    </tr>
    <tr>
      <td style="padding:28px 32px;">
        <p style="margin:0 0 12px;font-size:16px;color:#111827;">Hi {name},</p>
        <p style="margin:0 0 4px;font-size:15px;color:#374151;line-height:1.6;">
          Your payment for <strong>{job_name}</strong> has been disbursed.
        </p>
        <table cellpadding="0" cellspacing="0" border="0"
               style="width:100%;background:#ecfdf5;border-left:4px solid #057a55;
                      border-radius:4px;padding:14px 16px;margin:20px 0;">
          <tr>
            <td style="font-size:14px;color:#374151;line-height:1.7;">{body}</td>
          </tr>
        </table>
        <p style="margin:0;font-size:14px;color:#6b7280;">
          Thank you for your hard work. Your payment should reflect in your account shortly.
        </p>
      </td>
    </tr>
    <tr>
      <td style="background:#f9fafb;padding:14px 32px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
          Automated message from E-Movers &mdash; please do not reply to this email.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


# Map notification_type → HTML builder.
# Only types listed here trigger an email; all others are in-app only.
_HTML_BUILDERS = {
    "application_approved": _build_application_approved_html,
    "payment_disbursed": _build_payment_disbursed_html,
}


# ---------------------------------------------------------------------------
# Email dispatch (non-fatal)
# ---------------------------------------------------------------------------

def _send_email(recipient, notification_type: str, title: str, body: str, job=None) -> None:
    """
    Attempt to send an SMTP email for the given notification.

    Skips silently when:
      - EMAIL_HOST_USER is not configured (dev / CI safety net)
      - No HTML builder is registered for this notification_type
      - The recipient has no email address

    Exceptions are caught and logged — email failures never propagate.
    """
    if not getattr(settings, "EMAIL_HOST_USER", ""):
        return

    builder = _HTML_BUILDERS.get(notification_type)
    if builder is None:
        return

    recipient_email = getattr(recipient, "email", None)
    if not recipient_email:
        return

    try:
        html_message = builder(recipient, title, body, job)
        send_mail(
            subject=title,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send %s email to %s", notification_type, recipient_email
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def notify(recipient, notification_type: str, title: str, body: str, job=None) -> Notification:
    """
    Create a single in-app notification for one user and attempt an SMTP email.
    """
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        job=job,
    )
    _send_email(recipient, notification_type, title, body, job)
    return notification


def notify_many(recipients, notification_type: str, title: str, body: str, job=None) -> None:
    """
    Bulk-create in-app notifications and attempt an SMTP email per recipient.

    Recipients are materialised into a list once so the iterable can be
    traversed twice (bulk_create + email loop) without re-querying the DB.
    Email is sent individually so each person receives a personalised greeting.
    """
    recipient_list = list(recipients)

    Notification.objects.bulk_create([
        Notification(
            recipient=r,
            notification_type=notification_type,
            title=title,
            body=body,
            job=job,
        )
        for r in recipient_list
    ])

    for recipient in recipient_list:
        _send_email(recipient, notification_type, title, body, job)
