from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth + user management
    path("api/v1/", include("accounts.urls")),

    # Domain apps
    path("api/v1/customers/", include("customers.urls")),
    path("api/v1/fleet/", include("fleet.urls")),
    path("api/v1/jobs/", include("jobs.urls")),
    path("api/v1/billing/", include("billing.urls")),
    path("api/v1/reviews/", include("reviews.urls")),

    # New apps
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/attendance/", include("attendance.urls")),

    # Reporting
    path("api/v1/reports/", include("reports.urls")),
]
