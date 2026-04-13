from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from jobs.models import Job


class StaffReview(models.Model):
    """
    Post-job review submitted by the supervisor about a mover on the same job.

    Business rules (enforced at service layer):
      1. The reviewer must be the SUPERVISOR on the job.
      2. The reviewee must be a MOVER on the same job.
      3. A job must be COMPLETED before reviews can be submitted.
      4. One review per (job, reviewee) pair — enforced by unique_together.

    Effect:
      After each review is saved, a signal calls
      reviewee.staff_profile.recalculate_scores(), which recomputes
      average_rating and recommendation_score. The new score immediately
      influences the next auto_allocate_job call.
    """

    class Category(models.TextChoices):
        PUNCTUALITY = "punctuality", "Punctuality"
        TEAMWORK = "teamwork", "Teamwork"
        CARE_OF_GOODS = "care_of_goods", "Care of Goods"
        PHYSICAL_FITNESS = "physical_fitness", "Physical Fitness"
        COMMUNICATION = "communication", "Communication"
        OVERALL = "overall", "Overall"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_reviews",
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_reviews",
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OVERALL,
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 (very poor) to 5 (excellent).",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("job", "reviewee", "category")]
        ordering = ["-created_at"]
        verbose_name = "Staff Review"
        verbose_name_plural = "Staff Reviews"

    def __str__(self):
        return (
            f"Review by {self.reviewer.get_full_name()} "
            f"for {self.reviewee.get_full_name()} "
            f"on '{self.job.title}' — {self.rating}/5 ({self.category})"
        )
