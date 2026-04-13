from django.contrib import admin
from .models import StaffReview


@admin.register(StaffReview)
class StaffReviewAdmin(admin.ModelAdmin):
    list_display = [
        "id", "job", "reviewer", "reviewee",
        "category", "rating", "created_at",
    ]
    list_filter = ["category", "rating"]
    search_fields = [
        "reviewer__email", "reviewee__email",
        "job__title", "comment",
    ]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]
