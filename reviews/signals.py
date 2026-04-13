from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import StaffReview


@receiver(post_save, sender=StaffReview)
def update_staff_score_on_review_save(sender, instance, **kwargs):
    """
    After every StaffReview is created or updated, recompute the
    reviewee's average_rating and recommendation_score.

    This keeps recommendation_score always current — the next
    auto_allocate_job call will immediately benefit from the updated score.
    """
    profile = getattr(instance.reviewee, "staff_profile", None)
    if profile:
        profile.recalculate_scores()


@receiver(post_delete, sender=StaffReview)
def update_staff_score_on_review_delete(sender, instance, **kwargs):
    """
    If a review is deleted (e.g. by admin), recalculate scores so the
    recommendation_score reflects the remaining reviews.
    """
    profile = getattr(instance.reviewee, "staff_profile", None)
    if profile:
        profile.recalculate_scores()
