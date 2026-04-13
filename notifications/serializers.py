from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )
    job_title = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "type_display",
            "title",
            "body",
            "is_read",
            "job",
            "job_title",
            "created_at",
        ]
        read_only_fields = [
            "id", "notification_type", "title", "body", "job", "created_at",
        ]

    def get_job_title(self, obj):
        return obj.job.title if obj.job else None
