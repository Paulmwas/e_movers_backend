from django.contrib import admin
from .models import Job, JobAssignment, JobTruck


class JobAssignmentInline(admin.TabularInline):
    model = JobAssignment
    extra = 0
    readonly_fields = ["assigned_at", "assigned_by"]


class JobTruckInline(admin.TabularInline):
    model = JobTruck
    extra = 0
    readonly_fields = ["assigned_at", "assigned_by"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [
        "title", "customer", "status", "move_size",
        "scheduled_date", "created_by", "created_at",
    ]
    list_filter = ["status", "move_size", "scheduled_date"]
    search_fields = [
        "title",
        "customer__first_name",
        "customer__last_name",
        "customer__email",
    ]
    readonly_fields = ["created_by", "created_at", "updated_at", "started_at", "completed_at"]
    inlines = [JobAssignmentInline, JobTruckInline]
    ordering = ["-scheduled_date"]


@admin.register(JobAssignment)
class JobAssignmentAdmin(admin.ModelAdmin):
    list_display = ["job", "staff", "role", "assigned_at", "assigned_by"]
    list_filter = ["role"]
    readonly_fields = ["assigned_at"]


@admin.register(JobTruck)
class JobTruckAdmin(admin.ModelAdmin):
    list_display = ["job", "truck", "assigned_at", "assigned_by"]
    readonly_fields = ["assigned_at"]
