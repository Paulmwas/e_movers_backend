from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, StaffProfile


@receiver(post_save, sender=User)
def create_or_sync_staff_profile(sender, instance, created, **kwargs):
    """
    Auto-create a StaffProfile whenever a User with role=STAFF is saved.
    Handles both new user creation and role updates (e.g. admin demotes to staff).
    """
    if instance.role == User.Role.STAFF:
        StaffProfile.objects.get_or_create(user=instance)
