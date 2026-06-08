import io
from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.http import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

from .filters import JobFilter
from .models import Job, JobAssignment, JobApplication
from .serializers import (
    JobListSerializer,
    JobDetailSerializer,
    JobCreateSerializer,
    JobUpdateSerializer,
    AutoAllocateSerializer,
    ChangeTeamLeaderSerializer,
    AssignStaffSerializer,
    AssignTrucksSerializer,
    JobStatusSerializer,
    JobApplicationSerializer,
    ApproveApplicationsSerializer,
    PublicJobListSerializer,
    PublicApplySerializer,
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

User = get_user_model()


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

    POST body (all optional — defaults to job's requested_staff_count / requested_truck_count):
      {
        "num_movers": 3,    // override number of movers (excludes supervisor)
        "num_trucks": 1     // override number of trucks
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
                num_movers=serializer.validated_data.get("num_movers"),
                num_trucks=serializer.validated_data.get("num_trucks"),
            )
        except AllocationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Reload with full truck + staff details for the response
        updated_job = Job.objects.prefetch_related(
            "assignments__staff__staff_profile",
            "job_trucks__truck",
        ).get(pk=updated_job.pk)

        return Response(
            {
                "message": "Job allocated successfully.",
                "job": JobDetailSerializer(
                    updated_job,
                    context={"request": request},
                ).data,
            }
        )


class ChangeTeamLeaderView(APIView):
    """
    Admin only: swap the supervisor on an assigned or in-progress job.

    PATCH body:
      { "staff_id": <int> }

    The target staff member must already be assigned to this job as a mover.
    The current supervisor is demoted to mover; the target mover is promoted
    to supervisor.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def patch(self, request, pk):
        job = get_object_or_404(
            Job.objects.prefetch_related("assignments__staff"),
            pk=pk,
        )

        if job.status not in (Job.Status.ASSIGNED, Job.Status.IN_PROGRESS):
            return Response(
                {"error": "Team leader can only be changed on ASSIGNED or IN_PROGRESS jobs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ChangeTeamLeaderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_supervisor_id = serializer.validated_data["staff_id"]

        try:
            current_supervisor_assignment = job.assignments.get(role=JobAssignment.Role.SUPERVISOR)
        except JobAssignment.DoesNotExist:
            return Response(
                {"error": "This job has no supervisor assigned yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_supervisor_assignment.staff_id == new_supervisor_id:
            return Response(
                {"error": "This staff member is already the supervisor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_supervisor_assignment = job.assignments.get(
                staff_id=new_supervisor_id,
                role=JobAssignment.Role.MOVER,
            )
        except JobAssignment.DoesNotExist:
            return Response(
                {"error": "The target staff member is not assigned to this job as a mover."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_supervisor_assignment.role = JobAssignment.Role.MOVER
        current_supervisor_assignment.save(update_fields=["role"])

        new_supervisor_assignment.role = JobAssignment.Role.SUPERVISOR
        new_supervisor_assignment.save(update_fields=["role"])

        job.refresh_from_db()
        return Response(
            {
                "message": "Team leader updated successfully.",
                "job": JobDetailSerializer(job, context={"request": request}).data,
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


# ---------------------------------------------------------------------------
# PDF Export
# ---------------------------------------------------------------------------

class JobTeamPDFView(APIView):
    """
    Admin & Staff: download a PDF listing all team members assigned to a job.

    GET /api/v1/jobs/<pk>/team-pdf/

    Returns a PDF file with the job details and the full team roster
    (supervisor first, then movers alphabetically).
    """
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request, pk):
        job = get_object_or_404(
            Job.objects.select_related("customer")
            .prefetch_related("assignments__staff"),
            pk=pk,
        )

        assignments = list(job.assignments.select_related("staff").order_by("role", "staff__first_name"))

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=16, spaceAfter=6)
        heading_style = ParagraphStyle("heading", parent=styles["Heading2"], fontSize=12, spaceAfter=4)
        normal_style = styles["Normal"]

        elements = []

        elements.append(Paragraph("E-Movers — Team Assignment Sheet", title_style))
        elements.append(Spacer(1, 0.3 * cm))

        info_data = [
            ["Job", job.title],
            ["Customer", job.customer.get_full_name()],
            ["Date", str(job.scheduled_date)],
            ["Time", str(job.scheduled_time) if job.scheduled_time else "TBD"],
            ["Pickup", job.pickup_address],
            ["Drop-off", job.dropoff_address],
            ["Status", job.get_status_display()],
        ]

        info_table = Table(info_data, colWidths=[4 * cm, 13 * cm])
        info_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.5 * cm))

        elements.append(Paragraph(f"Team Members ({len(assignments)})", heading_style))

        team_data = [["#", "Name", "Role"]]
        for i, assignment in enumerate(assignments, start=1):
            team_data.append([
                str(i),
                assignment.staff.get_full_name(),
                assignment.get_role_display(),
            ])

        team_table = Table(team_data, colWidths=[1.5 * cm, 11 * cm, 4.5 * cm])
        team_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a56db")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        elements.append(team_table)

        doc.build(elements)
        buffer.seek(0)

        filename = f"team_{job.pk}_{job.scheduled_date}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")


# ---------------------------------------------------------------------------
# Public (no-auth) Views — staff availability form
# ---------------------------------------------------------------------------

class PublicPendingJobsView(generics.ListAPIView):
    """
    Public (no auth required): list all PENDING jobs open for applications.

    Staff use this to browse available work and decide where to apply.
    Returns limited fields — no customer contact details.

    GET /api/v1/jobs/public/
    """
    serializer_class = PublicJobListSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["scheduled_date"]
    ordering = ["scheduled_date"]

    def get_queryset(self):
        return (
            Job.objects.filter(status=Job.Status.PENDING)
            .prefetch_related("applications")
            .order_by("scheduled_date")
        )


class PublicApplyForJobView(APIView):
    """
    Public (no auth required): staff apply for or withdraw from a pending job
    using only their email address — no login needed.

    POST /api/v1/jobs/<pk>/public-apply/
      Body: { "email": "staff01@emovers.co.ke" }
      → Creates a JobApplication for the matching staff account.

    DELETE /api/v1/jobs/<pk>/public-apply/
      Body: { "email": "staff01@emovers.co.ke" }
      → Withdraws the existing APPLIED application.

    Business rules (same as authenticated flow):
      - Job must be PENDING
      - Deadline must not have passed (if set)
      - max_applicants cap must not be reached
      - Staff account must be active
      - Cannot apply twice for the same job
    """
    permission_classes = [AllowAny]

    def _get_staff(self, email):
        try:
            return User.objects.get(email=email, role=User.Role.STAFF, is_active=True)
        except User.DoesNotExist:
            return None

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        serializer = PublicApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        staff = self._get_staff(serializer.validated_data["email"])
        if not staff:
            return Response(
                {"error": "No active staff account found with that email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            application = apply_for_job(job=job, staff=staff)
        except ApplicationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Availability confirmed. The admin will review your application.",
                "application": {
                    "id": application.id,
                    "job": job.id,
                    "job_title": job.title,
                    "job_scheduled_date": str(job.scheduled_date),
                    "staff_name": staff.get_full_name(),
                    "status": application.status,
                    "applied_at": application.applied_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        serializer = PublicApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        staff = self._get_staff(serializer.validated_data["email"])
        if not staff:
            return Response(
                {"error": "No active staff account found with that email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            application = withdraw_application(job=job, staff=staff)
        except ApplicationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Availability withdrawn successfully.",
                "application": {
                    "id": application.id,
                    "job": job.id,
                    "job_title": job.title,
                    "status": application.status,
                },
            }
        )
