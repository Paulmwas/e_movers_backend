from django.urls import path
from . import views

urlpatterns = [
    path("", views.ReviewListView.as_view(), name="review_list"),
    path("create/", views.CreateReviewView.as_view(), name="review_create"),
    path("bulk-create/", views.BulkCreateReviewView.as_view(), name="review_bulk_create"),
    path("my-reviews/", views.MyReviewsView.as_view(), name="my_reviews"),
    path("staff/<int:pk>/summary/", views.StaffReviewSummaryView.as_view(), name="staff_review_summary"),
    path("job/<int:pk>/", views.JobReviewsView.as_view(), name="job_reviews"),
]
