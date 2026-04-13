from django.urls import path
from . import views

urlpatterns = [
    path("", views.JobListCreateView.as_view(), name="job_list_create"),
    path("unassigned/", views.UnassignedJobsView.as_view(), name="unassigned_jobs"),
    path("my-applications/", views.MyApplicationsView.as_view(), name="my_applications"),
    path("<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("<int:pk>/auto-allocate/", views.AutoAllocateView.as_view(), name="job_auto_allocate"),
    path("<int:pk>/assign-staff/", views.AssignStaffView.as_view(), name="job_assign_staff"),
    path("<int:pk>/assign-trucks/", views.AssignTrucksView.as_view(), name="job_assign_trucks"),
    path("<int:pk>/status/", views.JobStatusTransitionView.as_view(), name="job_status"),
    # Application flow
    path("<int:pk>/apply/", views.ApplyForJobView.as_view(), name="job_apply"),
    path("<int:pk>/applications/", views.JobApplicationsListView.as_view(), name="job_applications"),
    path("<int:pk>/approve-applications/", views.ApproveApplicationsView.as_view(), name="job_approve_applications"),
]
