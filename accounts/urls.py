from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change_password"),

    # User management (admin)
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/available-staff/", views.AvailableStaffView.as_view(), name="available_staff"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path("users/<int:pk>/staff-profile/", views.StaffProfileUpdateView.as_view(), name="staff_profile"),
]
