"""
reviews/services.py
===================
All review validation and creation logic.

Rules enforced here (not in the serializer or view):
  1. Job must be COMPLETED.
  2. Reviewer must be the SUPERVISOR on that job.
  3. Reviewee must be a MOVER on that same job (cannot review yourself or
     someone not on the job).
  4. One review per (job, reviewee, category) — unique_together on the model
     also guards this at the DB level, but we give a cleaner error here.
"""

from django.db import transaction
from jobs.models import Job, JobAssignment
from .models import StaffReview


class ReviewError(Exception):
    pass


@transaction.atomic
def create_review(
    *,
    job: Job,
    reviewer,
    reviewee,
    category: str,
    rating: int,
    comment: str = "",
) -> StaffReview:
    """
    Validate all business rules and create a StaffReview.

    Parameters
    ----------
    job       : The Job instance the review is for.
    reviewer  : The User submitting the review (must be supervisor).
    reviewee  : The User being reviewed (must be a mover on the job).
    category  : One of StaffReview.Category choices.
    rating    : Integer 1–5.
    comment   : Optional free-text feedback.

    Returns
    -------
    StaffReview instance (signal fires automatically to update scores).
    """

    # Rule 1: Job must be completed
    if job.status != Job.Status.COMPLETED:
        raise ReviewError(
            "Reviews can only be submitted for COMPLETED jobs. "
            f"This job is currently '{job.get_status_display()}'."
        )

    # Rule 2: Reviewer must be the supervisor on this job
    is_supervisor = job.assignments.filter(
        staff=reviewer,
        role=JobAssignment.Role.SUPERVISOR,
    ).exists()
    if not is_supervisor:
        raise ReviewError(
            "Only the job supervisor can submit reviews for this job."
        )

    # Rule 3: Reviewee must be a MOVER on this job (not supervisor, not outsider)
    is_mover = job.assignments.filter(
        staff=reviewee,
        role=JobAssignment.Role.MOVER,
    ).exists()
    if not is_mover:
        raise ReviewError(
            f"{reviewee.get_full_name()} is not a mover on this job "
            "and cannot be reviewed."
        )

    # Rule 4: No duplicate (job, reviewee, category)
    if StaffReview.objects.filter(job=job, reviewee=reviewee, category=category).exists():
        raise ReviewError(
            f"A '{category}' review for {reviewee.get_full_name()} "
            "on this job already exists."
        )

    return StaffReview.objects.create(
        job=job,
        reviewer=reviewer,
        reviewee=reviewee,
        category=category,
        rating=rating,
        comment=comment,
    )


def get_staff_review_summary(staff_user) -> dict:
    """
    Return a full review summary for a staff member including:
      - overall average rating
      - recommendation_score
      - total reviews
      - per-category breakdown
      - last 5 comments
    """
    from django.db.models import Avg, Count
    from accounts.models import StaffProfile

    reviews = StaffReview.objects.filter(reviewee=staff_user)

    # Per-category averages
    category_breakdown = (
        reviews.values("category")
        .annotate(avg_rating=Avg("rating"), count=Count("id"))
        .order_by("category")
    )

    # Last 5 comments
    recent_comments = list(
        reviews.exclude(comment="")
        .order_by("-created_at")
        .values("rating", "comment", "category", "created_at", "reviewer__first_name")[:5]
    )

    profile = getattr(staff_user, "staff_profile", None)

    return {
        "staff_id": staff_user.pk,
        "staff_name": staff_user.get_full_name(),
        "total_reviews": reviews.count(),
        "average_rating": float(profile.average_rating) if profile else 0,
        "recommendation_score": float(profile.recommendation_score) if profile else 1.0,
        "is_available": profile.is_available if profile else True,
        "category_breakdown": list(category_breakdown),
        "recent_comments": recent_comments,
    }
