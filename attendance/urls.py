from django.urls import path
from . import views

urlpatterns = [
    path("confirm/", views.ConfirmAttendanceView.as_view(), name="attendance_confirm"),
    path("generate-pin/<int:job_id>/", views.GeneratePinView.as_view(), name="attendance_generate_pin"),
    path("<int:job_id>/", views.JobAttendanceListView.as_view(), name="attendance_job_list"),
    path("<int:job_id>/mark-absent/", views.MarkAbsentView.as_view(), name="attendance_mark_absent"),
]
