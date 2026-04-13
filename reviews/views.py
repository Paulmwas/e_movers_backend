from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from .models import StaffReview
from .serializers import (
    StaffReviewSerializer,
    CreateReviewSerializer,
    BulkCreateReviewSerializer,
)
from .services import create_review, get_staff_review_summary, ReviewError
from jobs.models import Job
from accounts.permissions import IsMoverAdmin, IsAdminOrStaff, IsMoverStaff

User = get_user_model()


class CreateReviewView(APIView):
    """
    Staff (supervisor) only: submit a single review for a mover on a completed job.

    POST body:
      {
        "job_id": 1,
        "reviewee_id": 5,
        "category": "overall",
        "rating": 4,
        "comment": "Good worker, handled goods carefully."
      }

    The reviewer is always request.user — never passed in the body.
    All validation (supervisor check, mover check, completed job check)
    happens in reviews/services.py::create_review().
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        serializer = CreateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        job = get_object_or_404(
            Job.objects.prefetch_related("assignments"), pk=d["job_id"]
        )
        reviewee = get_object_or_404(User, pk=d["reviewee_id"])

        try:
            review = create_review(
                job=job,
                reviewer=request.user,
                reviewee=reviewee,
                category=d["category"],
                rating=d["rating"],
                comment=d.get("comment", ""),
            )
        except ReviewError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Review submitted successfully.",
                "review": StaffReviewSerializer(review).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BulkCreateReviewView(APIView):
    """
    Staff (supervisor) only: submit multiple reviews for a completed job in one shot.
    This is the primary endpoint used after a job finishes.

    POST body:
      {
        "job_id": 1,
        "reviews": [
          {"reviewee_id": 5, "category": "overall", "rating": 4, "comment": "..."},
          {"reviewee_id": 5, "category": "punctuality", "rating": 5},
          {"reviewee_id": 6, "category": "teamwork", "rating": 3}
        ]
      }

    Each review is validated independently. If ANY review fails validation,
    the entire batch is rejected (atomic). Successful reviews are returned
    in the response alongside per-item errors.
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        serializer = BulkCreateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        job = get_object_or_404(
            Job.objects.prefetch_related("assignments"), pk=d["job_id"]
        )

        created_reviews = []
        errors = []

        for item in d["reviews"]:
            reviewee = User.objects.filter(pk=item["reviewee_id"]).first()
            if not reviewee:
                errors.append({
                    "reviewee_id": item["reviewee_id"],
                    "error": f"User {item['reviewee_id']} does not exist.",
                })
                continue

            try:
                review = create_review(
                    job=job,
                    reviewer=request.user,
                    reviewee=reviewee,
                    category=item["category"],
                    rating=item["rating"],
                    comment=item.get("comment", ""),
                )
                created_reviews.append(review)
            except ReviewError as e:
                errors.append({
                    "reviewee_id": item["reviewee_id"],
                    "category": item["category"],
                    "error": str(e),
                })

        response_status = status.HTTP_201_CREATED if created_reviews else status.HTTP_400_BAD_REQUEST
        if created_reviews and errors:
            response_status = status.HTTP_207_MULTI_STATUS

        return Response(
            {
                "created": StaffReviewSerializer(created_reviews, many=True).data,
                "errors": errors,
                "summary": {
                    "total_submitted": len(d["reviews"]),
                    "created": len(created_reviews),
                    "failed": len(errors),
                },
            },
            status=response_status,
        )


class ReviewListView(generics.ListAPIView):
    """
    Admin only: list all reviews in the system with filters.

    Query params:
      ?job=<job_id>
      ?reviewee=<user_id>
      ?reviewer=<user_id>
      ?category=overall|punctuality|...
      ?rating=1..5
    """
    serializer_class = StaffReviewSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["job", "reviewer", "reviewee", "category", "rating"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return StaffReview.objects.select_related(
            "job", "reviewer", "reviewee"
        ).all()


class MyReviewsView(generics.ListAPIView):
    """
    Staff only: view all reviews received about themselves.
    Ordered by most recent first.
    """
    serializer_class = StaffReviewSerializer
    permission_classes = [IsAuthenticated, IsMoverStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["category", "rating", "job"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return StaffReview.objects.filter(
            reviewee=self.request.user
        ).select_related("job", "reviewer")


class StaffReviewSummaryView(APIView):
    """
    Admin & Staff: get a full review summary for a specific staff member.

    Returns:
      - Overall average rating
      - recommendation_score (drives auto-allocation priority)
      - Per-category breakdown
      - Last 5 comments
      - Availability status
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request, pk):
        staff = get_object_or_404(
            User.objects.select_related("staff_profile"),
            pk=pk,
            role="mover-staff",
        )
        summary = get_staff_review_summary(staff)
        return Response(summary)


class JobReviewsView(generics.ListAPIView):
    """
    Admin & Staff: list all reviews submitted for a specific job.
    Useful to see the full review session after a job is completed.
    """
    serializer_class = StaffReviewSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get_queryset(self):
        job_pk = self.kwargs["pk"]
        return StaffReview.objects.filter(
            job__pk=job_pk
        ).select_related("job", "reviewer", "reviewee")
