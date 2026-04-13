"""
attendance/views.py
===================
Attendance confirmation and management endpoints.
"""

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import AttendanceRecord
from .serializers import (
    AttendanceRecordSerializer,
    ConfirmAttendanceSerializer,
    MarkAbsentSerializer,
)
from .services import confirm_attendance, mark_absent, generate_attendance_pin, AttendanceError
from jobs.models import Job
from accounts.permissions import IsMoverAdmin, IsMoverStaff, IsAdminOrStaff


class ConfirmAttendanceView(APIView):
    """
    Staff only: confirm attendance by submitting the morning PIN.

    POST /api/v1/attendance/confirm/

    Request body:
      {
        "job_id": 1,
        "pin": "483921"
      }

    Creates an AttendanceRecord with status=CONFIRMED.
    """
    permission_classes = [IsAuthenticated, IsMoverStaff]

    def post(self, request):
        serializer = ConfirmAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = get_object_or_404(Job, pk=serializer.validated_data["job_id"])

        try:
            record = confirm_attendance(
                job=job,
                staff=request.user,
                token=serializer.validated_data["pin"],
            )
        except AttendanceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Attendance confirmed. See you on the move!",
                "record": AttendanceRecordSerializer(record).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GeneratePinView(APIView):
    """
    Admin only: generate a 6-digit attendance PIN for a job.
    Should be done on the morning of the move.

    POST /api/v1/attendance/generate-pin/<job_id>/

    No request body required.

    Response:
      { "pin": "483921", "job_id": 1, "message": "..." }
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id)

        try:
            pin = generate_attendance_pin(job=job)
        except AttendanceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"PIN generated for '{job.title}'. Share it with your team.",
                "job_id": job.pk,
                "pin": pin,
            }
        )


class JobAttendanceListView(generics.ListAPIView):
    """
    Admin & Staff: list all attendance records for a specific job.

    GET /api/v1/attendance/<job_id>/

    Returns confirmed + absent records so the admin can see who showed up.
    """
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get_queryset(self):
        job_id = self.kwargs["job_id"]
        return (
            AttendanceRecord.objects.filter(job_id=job_id)
            .select_related("staff", "confirmed_by", "job")
        )


class MarkAbsentView(APIView):
    """
    Admin only: mark a staff member as absent for a job.

    POST /api/v1/attendance/<job_id>/mark-absent/

    Request body:
      {
        "staff_id": 7,
        "notes": "Did not respond to calls"  // optional
      }
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def post(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id)
        serializer = MarkAbsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            record = mark_absent(
                job=job,
                staff_id=serializer.validated_data["staff_id"],
                recorded_by=request.user,
            )
            if serializer.validated_data.get("notes"):
                record.notes = serializer.validated_data["notes"]
                record.save(update_fields=["notes"])
        except AttendanceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"{record.staff.get_full_name()} has been marked as absent.",
                "record": AttendanceRecordSerializer(record).data,
            },
            status=status.HTTP_201_CREATED,
        )
