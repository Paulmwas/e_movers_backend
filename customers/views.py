from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Customer
from .serializers import CustomerSerializer, CustomerListSerializer
from accounts.permissions import IsMoverAdmin, IsAdminOrStaff


class CustomerListCreateView(generics.ListCreateAPIView):
    """
    GET  - Admin & Staff: list all customers (lightweight)
    POST - Admin only: create a new customer
    """
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "phone"]
    ordering_fields = ["created_at", "first_name", "last_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Customer.objects.select_related("created_by").all()

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CustomerListSerializer
        return CustomerSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsMoverAdmin()]
        return [IsAuthenticated(), IsAdminOrStaff()]


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    - Admin & Staff: retrieve a single customer
    PUT/PATCH - Admin only: update customer
    DELETE - Admin only: delete customer (blocked if active jobs exist)
    """
    queryset = Customer.objects.select_related("created_by").all()
    serializer_class = CustomerSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), IsAdminOrStaff()]
        return [IsAuthenticated(), IsMoverAdmin()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        active_statuses = ["pending", "assigned", "in_progress"]
        if instance.jobs.filter(status__in=active_statuses).exists():
            return Response(
                {"error": "Cannot delete a customer with active jobs. Complete or cancel their jobs first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response({"message": "Customer deleted successfully."}, status=status.HTTP_200_OK)
