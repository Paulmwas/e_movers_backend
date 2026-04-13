from django.contrib import admin
from .models import Truck


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = [
        "plate_number", "make", "model", "truck_type",
        "capacity_tons", "status", "mileage_km", "created_at",
    ]
    list_filter = ["status", "truck_type"]
    search_fields = ["plate_number", "make", "model"]
    readonly_fields = ["created_by", "created_at", "updated_at"]
    ordering = ["plate_number"]
