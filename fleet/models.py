from django.db import models
from django.conf import settings


class Truck(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ON_JOB = "on_job", "On Job"
        MAINTENANCE = "maintenance", "Maintenance"

    class TruckType(models.TextChoices):
        SMALL = "small", "Small (1-ton)"
        MEDIUM = "medium", "Medium (3-ton)"
        LARGE = "large", "Large (7-ton)"
        EXTRA_LARGE = "extra_large", "Extra Large (10-ton)"

    # Identity
    plate_number = models.CharField(max_length=20, unique=True)
    truck_type = models.CharField(max_length=20, choices=TruckType.choices)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=50, blank=True)

    # Specs
    capacity_tons = models.DecimalField(max_digits=5, decimal_places=2)

    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    mileage_km = models.PositiveIntegerField(default=0)
    last_service_date = models.DateField(null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)

    # Admin notes
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_trucks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plate_number"]
        verbose_name = "Truck"
        verbose_name_plural = "Trucks"

    def __str__(self):
        return f"{self.plate_number} — {self.make} {self.model} ({self.get_status_display()})"

    @property
    def is_available(self):
        return self.status == self.Status.AVAILABLE

    @property
    def display_name(self):
        return f"{self.plate_number} {self.make} {self.model} ({self.get_truck_type_display()})"
