"""
notifications/services.py
=========================
Helper functions for creating notifications. All other apps should
call these helpers — never create Notification objects directly.

Extending for real push/email delivery:
  Wrap notify() to also call your push provider or email backend.
  The model and API layer remain unchanged.
"""

from .models import Notification


def notify(recipient, notification_type: str, title: str, body: str, job=None) -> Notification:
    """
    Create a single in-app notification for one user.

    Parameters
    ----------
    recipient : User
    notification_type : str
        One of Notification.Type choices.
    title : str
    body : str
    job : Job | None
        Optional related job for context.

    Returns
    -------
    Notification
    """
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        job=job,
    )


def notify_many(recipients, notification_type: str, title: str, body: str, job=None) -> None:
    """
    Bulk-create notifications for a list of users.

    Parameters
    ----------
    recipients : iterable[User]
    notification_type : str
    title : str
    body : str
    job : Job | None
    """
    Notification.objects.bulk_create([
        Notification(
            recipient=r,
            notification_type=notification_type,
            title=title,
            body=body,
            job=job,
        )
        for r in recipients
    ])
