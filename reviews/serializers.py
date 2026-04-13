from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import StaffReview

User = get_user_model()


class StaffReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.SerializerMethodField()
    reviewee_name = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="job.title", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    rating_display = serializers.SerializerMethodField()

    class Meta:
        model = StaffReview
        fields = [
            "id",
            "job",
            "job_title",
            "reviewer",
            "reviewer_name",
            "reviewee",
            "reviewee_name",
            "category",
            "category_display",
            "rating",
            "rating_display",
            "comment",
            "created_at",
        ]
        read_only_fields = ["id", "reviewer", "created_at"]

    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name()

    def get_reviewee_name(self, obj):
        return obj.reviewee.get_full_name()

    def get_rating_display(self, obj):
        labels = {1: "Very Poor", 2: "Poor", 3: "Average", 4: "Good", 5: "Excellent"}
        return labels.get(obj.rating, str(obj.rating))


class CreateReviewSerializer(serializers.Serializer):
    """
    Request body for POST /reviews/create/

    The reviewer identity comes from request.user (JWT) — never from the body.
    All other business rules are enforced in reviews/services.py.
    """
    job_id = serializers.IntegerField()
    reviewee_id = serializers.IntegerField()
    category = serializers.ChoiceField(choices=StaffReview.Category.choices)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class BulkCreateReviewSerializer(serializers.Serializer):
    """
    Request body for POST /reviews/bulk-create/
    Allows a supervisor to submit reviews for all movers in one request.

    Body:
    {
      "job_id": 1,
      "reviews": [
        {"reviewee_id": 5, "category": "overall", "rating": 4, "comment": "..."},
        {"reviewee_id": 6, "category": "punctuality", "rating": 3},
        ...
      ]
    }
    """

    class ReviewItemSerializer(serializers.Serializer):
        reviewee_id = serializers.IntegerField()
        category = serializers.ChoiceField(choices=StaffReview.Category.choices)
        rating = serializers.IntegerField(min_value=1, max_value=5)
        comment = serializers.CharField(required=False, allow_blank=True, default="")

    job_id = serializers.IntegerField()
    reviews = ReviewItemSerializer(many=True, min_length=1)
