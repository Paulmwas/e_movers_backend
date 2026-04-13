from django.urls import path
from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification_list"),
    path("unread-count/", views.UnreadCountView.as_view(), name="notification_unread_count"),
    path("mark-all-read/", views.MarkAllReadView.as_view(), name="notification_mark_all_read"),
    path("<int:pk>/read/", views.MarkNotificationReadView.as_view(), name="notification_mark_read"),
]
