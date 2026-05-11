from django.contrib import admin
from .models import Job, JobAssignment, JobTruck, JobApplication


class JobAssignmentInline(admin.TabularInline):
    model = JobAssignment
    extra = 0
    readonly_fields = ["assigned_at", "assigned_by"]


class JobTruckInline(admin.TabularInline):
    model = JobTruck
    extra = 0
    readonly_fields = ["assigned_at", "assigned_by"]


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    readonly_fields = ["applied_at", "reviewed_at", "reviewed_by"]
    fields = ["staff", "status", "note", "applied_at", "reviewed_at", "reviewed_by"]


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
    inlines = [JobApplicationInline, JobAssignmentInline, JobTruckInline]
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


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ["job", "staff", "status", "applied_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status"]
    search_fields = [
        "job__title",
        "staff__first_name",
        "staff__last_name",
        "staff__email",
    ]
    readonly_fields = ["applied_at", "reviewed_at"]
    ordering = ["-applied_at"]
