from rest_framework.permissions import BasePermission
from .models import User


class IsMoverAdmin(BasePermission):
    """Allows access only to users with role=mover-admin."""
    message = "Access restricted to Mover Admins only."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsMoverStaff(BasePermission):
    """Allows access only to users with role=mover-staff."""
    message = "Access restricted to Mover Staff only."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.STAFF
        )


class IsAdminOrStaff(BasePermission):
    """Allows access to both mover-admin and mover-staff."""
    message = "Access restricted to authenticated staff or admin."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in [User.Role.ADMIN, User.Role.STAFF]
        )
