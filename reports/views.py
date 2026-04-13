"""
reports/views.py
================
Read-only aggregation endpoints for the admin dashboard.
No models needed — all data is queried from existing apps.

All endpoints are Admin-only.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncMonth, TruncDate
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import StaffProfile
from accounts.permissions import IsMoverAdmin
from billing.models import Invoice, Payment
from fleet.models import Truck
from jobs.models import Job, JobAssignment, JobApplication
from reviews.models import StaffReview

User = get_user_model()


def _parse_days(request, default=30) -> int:
    """Parse ?days=N query param, clamp to 1–365."""
    try:
        return max(1, min(int(request.query_params.get("days", default)), 365))
    except (ValueError, TypeError):
        return default


class DashboardSummaryView(APIView):
    """
    Admin only: high-level KPIs for the admin dashboard.

    Returns real-time counts and totals — designed to power stat cards.

    Query params:
      ?days=30  (default 30, max 365) — window for recent activity metrics
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        days = _parse_days(request)
        since = date.today() - timedelta(days=days)

        # --- User stats ---
        total_staff = User.objects.filter(role=User.Role.STAFF, is_active=True).count()
        available_staff = StaffProfile.objects.filter(is_available=True).count()
        on_job_staff = total_staff - available_staff

        # --- Fleet stats ---
        total_trucks = Truck.objects.count()
        available_trucks = Truck.objects.filter(status=Truck.Status.AVAILABLE).count()
        on_job_trucks = Truck.objects.filter(status=Truck.Status.ON_JOB).count()
        maintenance_trucks = Truck.objects.filter(status=Truck.Status.MAINTENANCE).count()

        # --- Job stats ---
        jobs_qs = Job.objects.all()
        job_counts = jobs_qs.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status=Job.Status.PENDING)),
            assigned=Count("id", filter=Q(status=Job.Status.ASSIGNED)),
            in_progress=Count("id", filter=Q(status=Job.Status.IN_PROGRESS)),
            completed=Count("id", filter=Q(status=Job.Status.COMPLETED)),
            cancelled=Count("id", filter=Q(status=Job.Status.CANCELLED)),
        )
        unassigned_jobs = (
            Job.objects.filter(status=Job.Status.PENDING)
            .exclude(assignments__isnull=False)
            .count()
        )
        recent_jobs = jobs_qs.filter(created_at__date__gte=since).count()

        # --- Billing stats ---
        invoice_qs = Invoice.objects.all()
        billing_totals = invoice_qs.aggregate(
            total_invoiced=Sum("total_amount"),
            total_collected=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )
        unpaid_count = invoice_qs.filter(
            payment_status=Invoice.PaymentStatus.UNPAID
        ).count()

        # --- Customer stats ---
        from customers.models import Customer
        total_customers = Customer.objects.count()
        recent_customers = Customer.objects.filter(created_at__date__gte=since).count()

        return Response({
            "window_days": days,
            "staff": {
                "total_active": total_staff,
                "available": available_staff,
                "on_job": on_job_staff,
            },
            "fleet": {
                "total": total_trucks,
                "available": available_trucks,
                "on_job": on_job_trucks,
                "maintenance": maintenance_trucks,
            },
            "jobs": {
                **job_counts,
                "unassigned_needing_attention": unassigned_jobs,
                f"created_last_{days}_days": recent_jobs,
            },
            "billing": {
                "total_invoiced": billing_totals["total_invoiced"] or Decimal("0.00"),
                "total_collected": billing_totals["total_collected"] or Decimal("0.00"),
                "total_outstanding": billing_totals["total_outstanding"] or Decimal("0.00"),
                "unpaid_invoices": unpaid_count,
            },
            "customers": {
                "total": total_customers,
                f"new_last_{days}_days": recent_customers,
            },
        })


class JobReportView(APIView):
    """
    Admin only: detailed job summary for a given time window.

    Query params:
      ?days=30   (default 30)

    Returns:
      - Status breakdown
      - Daily completion trend (last N days)
      - Move-size distribution
      - Average job duration (completed jobs only)
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        days = _parse_days(request)
        since = date.today() - timedelta(days=days)
        jobs = Job.objects.filter(created_at__date__gte=since)

        # Status breakdown
        status_breakdown = list(
            jobs.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        # Move-size distribution
        size_distribution = list(
            jobs.values("move_size")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Daily completion trend
        daily_completions = list(
            Job.objects.filter(
                status=Job.Status.COMPLETED,
                completed_at__date__gte=since,
            )
            .annotate(day=TruncDate("completed_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        # Average duration for completed jobs (in hours)
        completed = Job.objects.filter(
            status=Job.Status.COMPLETED,
            started_at__isnull=False,
            completed_at__isnull=False,
        )
        avg_duration_hours = None
        if completed.exists():
            durations = [
                (j.completed_at - j.started_at).total_seconds() / 3600
                for j in completed
                if j.completed_at and j.started_at
            ]
            if durations:
                avg_duration_hours = round(sum(durations) / len(durations), 2)

        # Unassigned jobs (always real-time regardless of window)
        unassigned = (
            Job.objects.filter(status=Job.Status.PENDING)
            .exclude(assignments__isnull=False)
            .values("id", "title", "scheduled_date", "move_size")
            .order_by("scheduled_date")
        )

        return Response({
            "window_days": days,
            "total_jobs_in_window": jobs.count(),
            "status_breakdown": status_breakdown,
            "move_size_distribution": size_distribution,
            "daily_completions": daily_completions,
            "average_job_duration_hours": avg_duration_hours,
            "unassigned_jobs": list(unassigned),
        })


class BillingReportView(APIView):
    """
    Admin only: revenue and payment summary.

    Query params:
      ?days=30   (default 30)

    Returns:
      - Revenue totals
      - Monthly revenue trend
      - Payment method breakdown
      - Top unpaid invoices
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        days = _parse_days(request)
        since = date.today() - timedelta(days=days)

        invoices = Invoice.objects.filter(created_at__date__gte=since)
        payments = Payment.objects.filter(
            payment_date__date__gte=since,
            status=Payment.Status.COMPLETED,
        )

        # Revenue totals
        revenue_totals = invoices.aggregate(
            total_invoiced=Sum("total_amount"),
            total_collected=Sum("amount_paid"),
            total_outstanding=Sum("balance_due"),
        )

        # Payment method breakdown
        method_breakdown = list(
            payments.values("method")
            .annotate(
                count=Count("id"),
                total=Sum("amount"),
            )
            .order_by("-total")
        )

        # Monthly revenue trend (last 6 months)
        monthly_trend = list(
            Invoice.objects.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                invoiced=Sum("total_amount"),
                collected=Sum("amount_paid"),
            )
            .order_by("-month")[:6]
        )

        # Payment status breakdown
        status_breakdown = list(
            invoices.values("payment_status")
            .annotate(count=Count("id"), total=Sum("total_amount"))
            .order_by("payment_status")
        )

        # Top 10 overdue / unpaid invoices
        unpaid_invoices = list(
            Invoice.objects.filter(
                payment_status__in=[
                    Invoice.PaymentStatus.UNPAID,
                    Invoice.PaymentStatus.PARTIAL,
                ]
            )
            .select_related("job__customer")
            .order_by("due_date", "-total_amount")
            .values(
                "id",
                "job__title",
                "job__customer__first_name",
                "job__customer__last_name",
                "total_amount",
                "balance_due",
                "payment_status",
                "due_date",
            )[:10]
        )

        return Response({
            "window_days": days,
            "revenue_totals": {
                "total_invoiced": revenue_totals["total_invoiced"] or Decimal("0.00"),
                "total_collected": revenue_totals["total_collected"] or Decimal("0.00"),
                "total_outstanding": revenue_totals["total_outstanding"] or Decimal("0.00"),
            },
            "payment_method_breakdown": method_breakdown,
            "monthly_revenue_trend": monthly_trend,
            "invoice_status_breakdown": status_breakdown,
            "top_unpaid_invoices": unpaid_invoices,
        })


class StaffPerformanceReportView(APIView):
    """
    Admin only: all active staff ranked by recommendation_score.
    This is the definitive view of how auto-allocation will prioritize staff.

    Query params:
      ?available_only=true  (default false) — filter to only available staff
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        available_only = request.query_params.get("available_only", "").lower() == "true"

        qs = (
            User.objects.filter(role=User.Role.STAFF, is_active=True)
            .select_related("staff_profile")
        )
        if available_only:
            qs = qs.filter(staff_profile__is_available=True)

        qs = qs.order_by("-staff_profile__recommendation_score")

        staff_data = []
        for user in qs:
            profile = getattr(user, "staff_profile", None)
            jobs_completed = JobAssignment.objects.filter(
                staff=user,
                job__status=Job.Status.COMPLETED,
            ).count()
            jobs_supervised = JobAssignment.objects.filter(
                staff=user,
                role=JobAssignment.Role.SUPERVISOR,
                job__status=Job.Status.COMPLETED,
            ).count()

            staff_data.append({
                "id": user.pk,
                "name": user.get_full_name(),
                "email": user.email,
                "phone": user.phone,
                "is_available": profile.is_available if profile else True,
                "average_rating": float(profile.average_rating) if profile else 0,
                "recommendation_score": float(profile.recommendation_score) if profile else 1.0,
                "total_reviews": profile.total_reviews if profile else 0,
                "jobs_completed": jobs_completed,
                "jobs_supervised": jobs_supervised,
            })

        return Response({
            "total_staff": len(staff_data),
            "staff": staff_data,
        })


class FleetReportView(APIView):
    """
    Admin only: fleet utilization report.

    Returns:
      - Status breakdown
      - Truck type distribution
      - Trucks currently on jobs (with job detail)
      - Trucks due for service
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        trucks = Truck.objects.all()

        # Status breakdown
        status_breakdown = list(
            trucks.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        # Type distribution
        type_distribution = list(
            trucks.values("truck_type")
            .annotate(count=Count("id"))
            .order_by("truck_type")
        )

        # Utilization rate
        total = trucks.count()
        on_job = trucks.filter(status=Truck.Status.ON_JOB).count()
        utilization_rate = round((on_job / total * 100), 2) if total > 0 else 0

        # Trucks currently on jobs
        from jobs.models import JobTruck
        on_job_details = list(
            JobTruck.objects.filter(
                job__status__in=[Job.Status.ASSIGNED, Job.Status.IN_PROGRESS]
            )
            .select_related("truck", "job__customer")
            .values(
                "truck__plate_number",
                "truck__make",
                "truck__model",
                "truck__truck_type",
                "job__id",
                "job__title",
                "job__status",
                "job__scheduled_date",
            )
        )

        # Trucks due for service (next_service_date <= today or overdue)
        due_for_service = list(
            trucks.filter(
                next_service_date__lte=date.today()
            ).values("id", "plate_number", "make", "model", "next_service_date", "status")
            .order_by("next_service_date")
        )

        return Response({
            "total_trucks": total,
            "utilization_rate_percent": utilization_rate,
            "status_breakdown": status_breakdown,
            "type_distribution": type_distribution,
            "currently_on_jobs": on_job_details,
            "due_for_service": due_for_service,
        })


class AttendanceReportView(APIView):
    """
    Admin only: attendance summary across all jobs in a time window.

    Query params:
      ?days=30   (default 30)

    Returns:
      - Overall confirmation rate
      - Per-job attendance summary (confirmed vs absent vs not-recorded)
      - Top absent staff
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        days = _parse_days(request)
        since = date.today() - timedelta(days=days)

        from attendance.models import AttendanceRecord

        records = AttendanceRecord.objects.filter(confirmed_at__date__gte=since)

        total_records = records.count()
        confirmed = records.filter(status=AttendanceRecord.Status.CONFIRMED).count()
        absent = records.filter(status=AttendanceRecord.Status.ABSENT).count()
        confirmation_rate = round((confirmed / total_records * 100), 2) if total_records > 0 else 0

        # Per-job breakdown
        per_job = list(
            records.values("job__id", "job__title", "job__scheduled_date")
            .annotate(
                confirmed=Count("id", filter=Q(status=AttendanceRecord.Status.CONFIRMED)),
                absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
                total=Count("id"),
            )
            .order_by("-job__scheduled_date")
        )

        # Top absent staff
        top_absent = list(
            records.filter(status=AttendanceRecord.Status.ABSENT)
            .values("staff__id", "staff__first_name", "staff__last_name", "staff__email")
            .annotate(absent_count=Count("id"))
            .order_by("-absent_count")[:10]
        )

        return Response({
            "window_days": days,
            "totals": {
                "total_records": total_records,
                "confirmed": confirmed,
                "absent": absent,
                "confirmation_rate_percent": confirmation_rate,
            },
            "per_job": per_job,
            "top_absent_staff": top_absent,
        })


class ApplicationsReportView(APIView):
    """
    Admin only: job application volume and approval rate report.

    Query params:
      ?days=30   (default 30)

    Returns:
      - Total applications in window
      - Status breakdown (applied/approved/rejected/withdrawn)
      - Approval rate
      - Top applicants by recommendation score
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get(self, request):
        days = _parse_days(request)
        since = date.today() - timedelta(days=days)

        applications = JobApplication.objects.filter(applied_at__date__gte=since)

        total = applications.count()
        status_breakdown = list(
            applications.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        approved = applications.filter(status=JobApplication.Status.APPROVED).count()
        approval_rate = round((approved / total * 100), 2) if total > 0 else 0

        # Most active applicants (by volume in window)
        top_applicants = list(
            applications.values(
                "staff__id",
                "staff__first_name",
                "staff__last_name",
                "staff__email",
            )
            .annotate(
                application_count=Count("id"),
                approved_count=Count("id", filter=Q(status=JobApplication.Status.APPROVED)),
            )
            .order_by("-application_count")[:10]
        )

        # Jobs with open (APPLIED) applications still unreviewed
        open_applications_by_job = list(
            JobApplication.objects.filter(status=JobApplication.Status.APPLIED)
            .values("job__id", "job__title", "job__scheduled_date", "job__status")
            .annotate(open_count=Count("id"))
            .order_by("job__scheduled_date")
        )

        return Response({
            "window_days": days,
            "total_applications": total,
            "status_breakdown": status_breakdown,
            "approval_rate_percent": approval_rate,
            "top_applicants": top_applicants,
            "jobs_with_open_applications": open_applications_by_job,
        })
