from rest_framework import serializers
from .models import AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_email = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    confirmed_by_name = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="job.title", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "job",
            "job_title",
            "staff",
            "staff_name",
            "staff_email",
            "status",
            "status_display",
            "confirmed_at",
            "confirmed_by",
            "confirmed_by_name",
            "notes",
        ]
        read_only_fields = [
            "id", "job", "staff", "status", "confirmed_at", "confirmed_by",
        ]

    def get_staff_name(self, obj):
        return obj.staff.get_full_name()

    def get_staff_email(self, obj):
        return obj.staff.email

    def get_confirmed_by_name(self, obj):
        return obj.confirmed_by.get_full_name() if obj.confirmed_by else None


class ConfirmAttendanceSerializer(serializers.Serializer):
    """Request body for POST /attendance/confirm/"""
    job_id = serializers.IntegerField()
    pin = serializers.CharField(
        min_length=6, max_length=6,
        help_text="6-digit attendance PIN provided by the admin.",
    )


class MarkAbsentSerializer(serializers.Serializer):
    """Request body for POST /attendance/<job_id>/mark-absent/"""
    staff_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
