"""
notifications/views.py
======================
Endpoints for in-app notifications. All endpoints are scoped to the
authenticated user — staff only see their own notifications.
"""

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """
    Auth: list own notifications, newest first.

    GET /api/v1/notifications/

    Query params:
      ?is_read=true|false  — filter by read status
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")
        return qs


class MarkNotificationReadView(APIView):
    """
    Auth: mark a single notification as read.

    PATCH /api/v1/notifications/<pk>/read/
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        notification = get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    """
    Auth: mark all own notifications as read.

    POST /api/v1/notifications/mark-all-read/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True)
        return Response(
            {"message": f"{updated} notification(s) marked as read."}
        )


class UnreadCountView(APIView):
    """
    Auth: fast unread count for notification badge.

    GET /api/v1/notifications/unread-count/

    Response: { "count": N }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({"count": count})
