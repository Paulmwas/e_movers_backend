from django.contrib.auth import get_user_model, authenticate
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from .models import StaffProfile
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
    StaffProfileSerializer,
)
from .permissions import IsMoverAdmin, IsAdminOrStaff

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["email"] = user.email
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class RegisterView(generics.CreateAPIView):
    """
    Admin-only: create a new mover-admin or mover-staff account.
    Self-registration is intentionally disabled; only admins onboard users.
    """
    serializer_class = RegisterSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Account created successfully.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Authenticate with email + password, receive JWT tokens."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pre-check for inactive account. Django's authenticate() returns None
        # for BOTH wrong password AND inactive users, making them indistinguishable.
        # We look up the user first so we can return the correct HTTP status.
        try:
            candidate = User.objects.get(email=serializer.validated_data["email"])
            if not candidate.is_active:
                return Response(
                    {"error": "Account is deactivated. Contact admin."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except User.DoesNotExist:
            pass

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        if not user:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = get_tokens_for_user(user)
        return Response(
            {
                "message": "Login successful.",
                "user": UserSerializer(user).data,
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """Blacklist the refresh token, effectively ending the session."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get("refresh"))
            token.blacklist()
            return Response({"message": "Logged out successfully."})
        except Exception:
            return Response(
                {"error": "Invalid or missing refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class MeView(APIView):
    """
    GET  /auth/me/ - return authenticated user's profile
    PATCH /auth/me/ - update own first_name, last_name, phone
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Authenticated user changes their own password."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"error": "Old password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"message": "Password changed successfully."})


# ---------------------------------------------------------------------------
# User management (admin)
# ---------------------------------------------------------------------------

class UserListView(generics.ListAPIView):
    """
    Admin-only: list all users.
    Query params:
      ?role=mover-admin|mover-staff
      ?is_active=true|false
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["date_joined", "first_name", "last_name"]
    ordering = ["-date_joined"]

    def get_queryset(self):
        qs = User.objects.select_related("staff_profile").all()
        role = self.request.query_params.get("role")
        is_active = self.request.query_params.get("is_active")
        if role:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        return qs


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Admin-only: retrieve, update, or soft-delete any user.
    DELETE performs a soft-delete (sets is_active=False).
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]
    queryset = User.objects.select_related("staff_profile").all()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = UserUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            return Response(
                {"error": "You cannot deactivate your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response({"message": "User deactivated."}, status=status.HTTP_200_OK)


class StaffProfileUpdateView(APIView):
    """
    Admin-only: update a staff member's profile (availability, notes).
    Rating and recommendation_score are read-only; they update via reviews.
    """
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get_object(self, pk):
        try:
            return StaffProfile.objects.select_related("user").get(user__pk=pk)
        except StaffProfile.DoesNotExist:
            return None

    def get(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response(
                {"error": "Staff profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(StaffProfileSerializer(profile).data)

    def patch(self, request, pk):
        profile = self.get_object(pk)
        if not profile:
            return Response(
                {"error": "Staff profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = StaffProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AvailableStaffView(generics.ListAPIView):
    """
    Admin-only: list all staff who are currently available for assignment.
    Ordered by recommendation_score (best candidates first).
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsMoverAdmin]

    def get_queryset(self):
        return (
            User.objects.filter(
                role=User.Role.STAFF,
                is_active=True,
                staff_profile__is_available=True,
            )
            .select_related("staff_profile")
            .order_by("-staff_profile__recommendation_score")
        )
