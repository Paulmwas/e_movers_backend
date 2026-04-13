from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .filters import JobFilter
from .models import Job, JobAssignment, JobApplication
from .serializers import (
    JobListSerializer,
    JobDetailSerializer,
    JobCreateSerializer,
    JobUpdateSerializer,
    AutoAllocateSerializer,
    AssignStaffSerializer,
    AssignTrucksSerializer,
    JobStatusSerializer,
    JobApplicationSerializer,
    ApproveApplicationsSerializer,
)
from .services import (
    auto_allocate_job,
    assign_staff_to_job,
    assign_trucks_to_job,
    transition_job_status,
    apply_for_job,
    withdraw_application,
    approve_applications,
    AllocationError,
    StatusTransitionError,
    ApplicationError,
)
from accounts.permissions import IsMoverAdmin, IsAdminOrStaff, IsMoverStaff


class JobListCreateView(generics.ListCreateAPIView):
    """
    GET  — Admin & Staff: list jobs with filters
    POST — Admin only: create a new job

    Query params:
      ?status=pending|assigned|in_progress|completed|cancelled
      ?customer=<id>
      ?scheduled_date=YYYY-MM-DD
      ?search=<title|customer name>
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobFilter
    search_fields = [
        "title",
        "customer__first_name",
        "customer__last_name",
        "customer__email",
        "pickup_address",
        "dropoff_address",
    ]
    ordering_fields = ["scheduled_date", "created_at", "status"]
    ordering = ["-scheduled_date", "-created_at"]

    def get_queryset(self):
        return (
            Job.objects.select_related("customer", "created_by")
            .prefetch_related("assignments", "job_trucks")
            .all()
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JobCreateSerializer
        return JobListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsMoverAdmin()]
        return [IsAuthenticated(), IsAdminOrStaff()]

    def create(self, request, *args, **kwargs):
        serializer = JobCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        return Response(
            JobDetailSerializer(job, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET        — Admin & Staff: full job detail with assignments + trucks
    PUT/PATCH  — Admin only: update job fields (blocked on completed/cancelled)
    DELETE     — Admin only: blocked if job is in_progress or completed
    """
    queryset = (
        Job.objects.select_related("customer", "created_by")
        .prefetch_related(
            "assignments__staff__staff_profile",
            "job_trucks__truck",
        )
    )

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return JobUpdateSerializer
        return JobDetailSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), IsAdminOrStaff()]
        return [IsAuthenticated(), IsMoverAdmin()]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status in (Job.Status.COMPLETED, Job.Status.CANCELLED):
            return Response(
                {"error": f"Cannot edit a job with status '{instance.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        partial = kwargs.pop("partial", False)
        serializer = JobUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            JobDetailSerializer(instance, context={"request": request}).data
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status in (Job.Status.IN_PROGRESS, Job.Status.COMPLETED):
            return Response(
                {"error": f"Cannot delete a job with status '{instance.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response({"message": "Job deleted successfully."}, status=status.HTTP_200_OK)


class UnassignedJobsView(generics.ListAPIView):
    """
    Admin & Staff: highlight all PENDING jobs that have NO staff/truck assignment yet.
    These are the jobs that need attention.
    """
    serializer_class = JobListSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get_queryset(self):
        # Pending jobs that have no assignments at all
        return (
            Job.objects.filter(status=Job.Status.PENDING)
            .exclude(assignments__isnull=False)
            .select_related("customer")
            .prefetch_related("assignments", "job_trucks")
            .order_by("scheduled_date")
        )


class AutoAllocateView(APIView):
    """
    Admin only: auto-allocate staff and trucks to a job.

    POST body (optional):
      {
        "num_movers": 10,   // default 10
        "num_trucks": 1     // default 1
      }

    Selects staff ordered by recommendation_score DESC, assigns the
    top candidate as supervisor and the rest as movers.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        job = get_object_or_404(
            Job.objects.prefetch_related("assignments", "job_trucks"), pk=pk
        )
        serializer = AutoAllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_job = auto_allocate_job(
                job=job,
                requested_by=request.user,
                num_movers=serializer.validated_data["num_movers"],
                num_trucks=serializer.validated_data["num_trucks"],
            )
        except AllocationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Job allocated successfully.",
                "job": JobDetailSerializer(
                    updated_job,
                    context={"request": request},
                ).data,
            }
        )


class AssignStaffView(APIView):
    """
    Admin only: manually assign specific staff members to a job.

    POST body:
      { "staff_ids": [1, 2, 3, ...] }
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        serializer = AssignStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_job = assign_staff_to_job(
                job=job,
                staff_ids=serializer.validated_data["staff_ids"],
                requested_by=request.user,
            )
        except AllocationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Staff assigned successfully.",
                "job": JobDetailSerializer(
                    updated_job,
                    context={"request": request},
                ).data,
            }
        )


class AssignTrucksView(APIView):
    """
    Admin only: manually assign specific trucks to a job.

    POST body:
      { "truck_ids": [1, 2] }
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        serializer = AssignTrucksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_job = assign_trucks_to_job(
                job=job,
                truck_ids=serializer.validated_data["truck_ids"],
                requested_by=request.user,
            )
        except AllocationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Trucks assigned successfully.",
                "job": JobDetailSerializer(
                    updated_job,
                    context={"request": request},
                ).data,
            }
        )


class JobStatusTransitionView(APIView):
    """
    Admin & Staff: transition a job through its status machine.

    POST body:
      { "action": "start" | "complete" | "cancel" }

    Only the supervisor or an admin can start/complete a job.
    Staff can only act on jobs they are assigned to.
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request, pk):
        job = get_object_or_404(
            Job.objects.prefetch_related("assignments__staff", "job_trucks__truck"),
            pk=pk,
        )
        serializer = JobStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.get_new_status()

        # Staff can only act on jobs they are assigned to
        if request.user.is_mover_staff:
            is_assigned = job.assignments.filter(staff=request.user).exists()
            if not is_assigned:
                return Response(
                    {"error": "You are not assigned to this job."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Staff can only start or complete; cancellation is admin-only
            if new_status == Job.Status.CANCELLED:
                return Response(
                    {"error": "Only admins can cancel a job."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Only the supervisor can complete a job
            if new_status == Job.Status.COMPLETED:
                is_supervisor = job.assignments.filter(
                    staff=request.user, role=JobAssignment.Role.SUPERVISOR
                ).exists()
                if not is_supervisor:
                    return Response(
                        {"error": "Only the job supervisor can mark a job as completed."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        try:
            updated_job = transition_job_status(
                job=job,
                new_status=new_status,
                requested_by=request.user,
            )
        except StatusTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"Job status updated to '{updated_job.get_status_display()}'.",
                "job": JobDetailSerializer(
                    updated_job,
                    context={"request": request},
                ).data,
            }
        )


# ---------------------------------------------------------------------------
# Job Application Views
# ---------------------------------------------------------------------------

class ApplyForJobView(APIView):
    """
    Staff only: apply for or withdraw from a pending job.

    POST — Apply for the job.
    DELETE — Withdraw an existing APPLIED application.
    """
    permission_classes = [IsAuthenticated, IsMoverStaff]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        try:
            application = apply_for_job(job=job, staff=request.user)
        except ApplicationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "message": "Application submitted successfully.",
                "application": JobApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        try:
            application = withdraw_application(job=job, staff=request.user)
        except ApplicationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "message": "Application withdrawn.",
                "application": JobApplicationSerializer(application).data,
            }
        )


class JobApplicationsListView(generics.ListAPIView):
    """
    Admin only: list all applicants for a specific job, ordered by
    recommendation_score descending so the best candidates appear first.

    GET /api/v1/jobs/<pk>/applications/

    Query params:
      ?status=applied|approved|rejected|withdrawn
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["applied_at"]
    ordering = ["-applied_at"]

    def get_queryset(self):
        job_pk = self.kwargs["pk"]
        return (
            JobApplication.objects.filter(job_id=job_pk)
            .select_related("staff__staff_profile", "reviewed_by")
            .order_by("-staff__staff_profile__recommendation_score", "-applied_at")
        )


class ApproveApplicationsView(APIView):
    """
    Admin only: approve a subset of applicants, designate a supervisor,
    auto-reject the rest, and transition the job to ASSIGNED.

    POST body:
      {
        "approved_staff_ids": [3, 7, 12, ...],
        "supervisor_id": 7
      }

    All approved staff receive a success notification with the team list.
    Rejected applicants receive a rejection notification.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, pk):
        job = get_object_or_404(
            Job.objects.prefetch_related("applications__staff__staff_profile"),
            pk=pk,
        )
        serializer = ApproveApplicationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_job = approve_applications(
                job=job,
                approved_staff_ids=serializer.validated_data["approved_staff_ids"],
                supervisor_id=serializer.validated_data["supervisor_id"],
                reviewed_by=request.user,
            )
        except ApplicationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Applications approved. Job is now ASSIGNED.",
                "job": JobDetailSerializer(
                    updated_job, context={"request": request}
                ).data,
            }
        )


class MyApplicationsView(generics.ListAPIView):
    """
    Staff only: list own job application history, newest first.

    GET /api/v1/jobs/my-applications/

    Query params:
      ?status=applied|approved|rejected|withdrawn
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated, IsMoverStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["applied_at"]
    ordering = ["-applied_at"]

    def get_queryset(self):
        return (
            JobApplication.objects.filter(staff=self.request.user)
            .select_related("job__customer", "reviewed_by")
        )
