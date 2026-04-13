from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import StaffProfile

User = get_user_model()


class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = [
            "is_available",
            "average_rating",
            "total_reviews",
            "recommendation_score",
            "notes",
            "updated_at",
        ]
        read_only_fields = [
            "average_rating",
            "total_reviews",
            "recommendation_score",
            "updated_at",
        ]


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    staff_profile = StaffProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "is_active",
            "date_joined",
            "staff_profile",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()


class RegisterSerializer(serializers.ModelSerializer):
    """Admin-only: create a new staff or admin user account."""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate_role(self, value):
        allowed = [User.Role.ADMIN, User.Role.STAFF]
        if value not in allowed:
            raise serializers.ValidationError(
                f"Role must be one of: {', '.join(allowed)}"
            )
        return value

    def validate(self, data):
        if data["password"] != data.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    """Partial update for user fields editable by admin."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "is_active"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return data
