from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Truck
from .serializers import TruckSerializer, TruckListSerializer, TruckUpdateSerializer
from accounts.permissions import IsMoverAdmin, IsAdminOrStaff


class TruckListCreateView(generics.ListCreateAPIView):
    """
    GET  — Admin & Staff: list trucks with optional filters
    POST — Admin only: register a new truck

    Query params:
      ?status=available|on_job|maintenance
      ?truck_type=small|medium|large|extra_large
      ?search=<plate|make|model>
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "truck_type"]
    search_fields = ["plate_number", "make", "model"]
    ordering_fields = ["plate_number", "capacity_tons", "created_at"]
    ordering = ["plate_number"]

    def get_queryset(self):
        return Truck.objects.select_related("created_by").all()

    def get_serializer_class(self):
        if self.request.method == "GET":
            return TruckListSerializer
        return TruckSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsMoverAdmin()]
        return [IsAuthenticated(), IsAdminOrStaff()]


class TruckDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET        — Admin & Staff: full truck detail
    PUT/PATCH  — Admin only: update truck fields
    DELETE     — Admin only: blocked if truck is currently on a job
    """
    queryset = Truck.objects.select_related("created_by").all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return TruckUpdateSerializer
        return TruckSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), IsAdminOrStaff()]
        return [IsAuthenticated(), IsMoverAdmin()]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = TruckUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TruckSerializer(instance, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == Truck.Status.ON_JOB:
            return Response(
                {"error": "Cannot delete a truck that is currently on a job."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response({"message": "Truck deleted successfully."}, status=status.HTTP_200_OK)


class AvailableTrucksView(generics.ListAPIView):
    """
    Admin & Staff: list only trucks with status=available.
    Ordered by capacity_tons descending (largest first, preferred for auto-allocation).
    """
    serializer_class = TruckListSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get_queryset(self):
        return (
            Truck.objects.filter(status=Truck.Status.AVAILABLE)
            .order_by("-capacity_tons")
        )
