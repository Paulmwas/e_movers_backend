from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "address",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — avoids over-fetching."""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ["id", "full_name", "email", "phone", "created_at"]

    def get_full_name(self, obj):
        return obj.get_full_name()
