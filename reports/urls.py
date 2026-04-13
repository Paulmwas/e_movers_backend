from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.DashboardSummaryView.as_view(), name="report_dashboard"),
    path("jobs/", views.JobReportView.as_view(), name="report_jobs"),
    path("billing/", views.BillingReportView.as_view(), name="report_billing"),
    path("staff-performance/", views.StaffPerformanceReportView.as_view(), name="report_staff_performance"),
    path("fleet/", views.FleetReportView.as_view(), name="report_fleet"),
    path("attendance/", views.AttendanceReportView.as_view(), name="report_attendance"),
    path("applications/", views.ApplicationsReportView.as_view(), name="report_applications"),
]
