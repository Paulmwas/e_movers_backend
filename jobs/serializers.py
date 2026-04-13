from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Job, JobAssignment, JobTruck, JobApplication
from customers.serializers import CustomerListSerializer
from fleet.serializers import TruckListSerializer

User = get_user_model()


class JobAssignmentSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_email = serializers.SerializerMethodField()
    staff_phone = serializers.SerializerMethodField()
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    recommendation_score = serializers.SerializerMethodField()

    class Meta:
        model = JobAssignment
        fields = [
            "id",
            "staff",
            "staff_name",
            "staff_email",
            "staff_phone",
            "role",
            "role_display",
            "recommendation_score",
            "assigned_at",
        ]

    def get_staff_name(self, obj):
        return obj.staff.get_full_name()

    def get_staff_email(self, obj):
        return obj.staff.email

    def get_staff_phone(self, obj):
        return obj.staff.phone

    def get_recommendation_score(self, obj):
        profile = getattr(obj.staff, "staff_profile", None)
        return float(profile.recommendation_score) if profile else None


class JobTruckSerializer(serializers.ModelSerializer):
    plate_number = serializers.CharField(source="truck.plate_number", read_only=True)
    truck_type = serializers.CharField(source="truck.get_truck_type_display", read_only=True)
    make = serializers.CharField(source="truck.make", read_only=True)
    model = serializers.CharField(source="truck.model", read_only=True)
    capacity_tons = serializers.DecimalField(
        source="truck.capacity_tons", max_digits=5, decimal_places=2, read_only=True
    )

    class Meta:
        model = JobTruck
        fields = [
            "id",
            "truck",
            "plate_number",
            "truck_type",
            "make",
            "model",
            "capacity_tons",
            "assigned_at",
        ]


class JobListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    customer_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    move_size_display = serializers.CharField(source="get_move_size_display", read_only=True)
    is_unassigned = serializers.BooleanField(read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "customer",
            "customer_name",
            "status",
            "status_display",
            "move_size",
            "move_size_display",
            "scheduled_date",
            "scheduled_time",
            "is_unassigned",
            "assigned_staff_count",
            "assigned_truck_count",
            "created_at",
        ]

    def get_customer_name(self, obj):
        return obj.customer.get_full_name()


class JobDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with nested assignments and trucks."""
    customer_detail = CustomerListSerializer(source="customer", read_only=True)
    assignments = JobAssignmentSerializer(many=True, read_only=True)
    trucks = JobTruckSerializer(source="job_trucks", many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    move_size_display = serializers.CharField(source="get_move_size_display", read_only=True)
    is_unassigned = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "customer",
            "customer_detail",
            "status",
            "status_display",
            "move_size",
            "move_size_display",
            "pickup_address",
            "dropoff_address",
            "estimated_distance_km",
            "scheduled_date",
            "scheduled_time",
            "started_at",
            "completed_at",
            "requested_staff_count",
            "requested_truck_count",
            "assigned_staff_count",
            "assigned_truck_count",
            "is_unassigned",
            "notes",
            "special_instructions",
            "application_deadline",
            "max_applicants",
            "assignments",
            "trucks",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "started_at",
            "completed_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class JobCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new job (admin only)."""

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "customer",
            "move_size",
            "pickup_address",
            "dropoff_address",
            "estimated_distance_km",
            "scheduled_date",
            "scheduled_time",
            "requested_staff_count",
            "requested_truck_count",
            "application_deadline",
            "max_applicants",
            "notes",
            "special_instructions",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class JobUpdateSerializer(serializers.ModelSerializer):
    """Fields an admin can edit after creation (pre-completion)."""

    class Meta:
        model = Job
        fields = [
            "title",
            "move_size",
            "pickup_address",
            "dropoff_address",
            "estimated_distance_km",
            "scheduled_date",
            "scheduled_time",
            "requested_staff_count",
            "requested_truck_count",
            "application_deadline",
            "max_applicants",
            "notes",
            "special_instructions",
        ]


# ---------------------------------------------------------------------------
# Action request serializers
# ---------------------------------------------------------------------------

class AutoAllocateSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/auto-allocate/"""
    num_movers = serializers.IntegerField(min_value=1, max_value=50, default=10)
    num_trucks = serializers.IntegerField(min_value=1, max_value=10, default=1)


class AssignStaffSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/assign-staff/"""
    staff_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        allow_empty=False,
    )


class AssignTrucksSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/assign-trucks/"""
    truck_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        allow_empty=False,
    )


class JobStatusSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/status/"""
    action = serializers.ChoiceField(
        choices=["start", "complete", "cancel"]
    )

    ACTION_TO_STATUS = {
        "start": Job.Status.IN_PROGRESS,
        "complete": Job.Status.COMPLETED,
        "cancel": Job.Status.CANCELLED,
    }

    def get_new_status(self):
        return self.ACTION_TO_STATUS[self.validated_data["action"]]


# ---------------------------------------------------------------------------
# Job Application serializers
# ---------------------------------------------------------------------------

class JobApplicationSerializer(serializers.ModelSerializer):
    """Full representation of a job application."""
    staff_name = serializers.SerializerMethodField()
    staff_email = serializers.SerializerMethodField()
    staff_phone = serializers.SerializerMethodField()
    recommendation_score = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    job_scheduled_date = serializers.DateField(source="job.scheduled_date", read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "job",
            "job_title",
            "job_scheduled_date",
            "staff",
            "staff_name",
            "staff_email",
            "staff_phone",
            "recommendation_score",
            "average_rating",
            "status",
            "status_display",
            "applied_at",
            "reviewed_at",
            "reviewed_by",
            "note",
        ]
        read_only_fields = [
            "id", "staff", "job", "applied_at", "reviewed_at", "reviewed_by",
            "status",
        ]

    def get_staff_name(self, obj):
        return obj.staff.get_full_name()

    def get_staff_email(self, obj):
        return obj.staff.email

    def get_staff_phone(self, obj):
        return obj.staff.phone

    def get_recommendation_score(self, obj):
        profile = getattr(obj.staff, "staff_profile", None)
        return float(profile.recommendation_score) if profile else None

    def get_average_rating(self, obj):
        profile = getattr(obj.staff, "staff_profile", None)
        return float(profile.average_rating) if profile else None


class ApproveApplicationsSerializer(serializers.Serializer):
    """Request body for POST /jobs/<pk>/approve-applications/"""
    approved_staff_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        allow_empty=False,
        help_text="List of User PKs to approve. Must all have an APPLIED application.",
    )
    supervisor_id = serializers.IntegerField(
        help_text="User PK of the chosen supervisor. Must be in approved_staff_ids.",
    )

    def validate(self, data):
        if data["supervisor_id"] not in data["approved_staff_ids"]:
            raise serializers.ValidationError(
                {"supervisor_id": "Supervisor must be in the approved_staff_ids list."}
            )
        return data
