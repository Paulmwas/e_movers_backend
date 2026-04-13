from rest_framework import serializers
from .models import Truck


class TruckSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    truck_type_display = serializers.CharField(source="get_truck_type_display", read_only=True)

    class Meta:
        model = Truck
        fields = [
            "id",
            "plate_number",
            "truck_type",
            "truck_type_display",
            "make",
            "model",
            "year",
            "color",
            "capacity_tons",
            "status",
            "status_display",
            "mileage_km",
            "last_service_date",
            "next_service_date",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class TruckListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    truck_type_display = serializers.CharField(source="get_truck_type_display", read_only=True)

    class Meta:
        model = Truck
        fields = [
            "id",
            "plate_number",
            "truck_type",
            "truck_type_display",
            "make",
            "model",
            "capacity_tons",
            "status",
            "status_display",
        ]


class TruckUpdateSerializer(serializers.ModelSerializer):
    """Fields an admin can edit after creation."""

    class Meta:
        model = Truck
        fields = [
            "make",
            "model",
            "year",
            "color",
            "capacity_tons",
            "status",
            "mileage_km",
            "last_service_date",
            "next_service_date",
            "notes",
        ]
