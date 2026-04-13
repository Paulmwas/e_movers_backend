from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, StaffProfile


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    verbose_name_plural = "Staff Profile"
    readonly_fields = ["average_rating", "total_reviews", "recommendation_score", "updated_at"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "get_full_name", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-date_joined"]
    readonly_fields = ["date_joined"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("date_joined",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "phone", "password1", "password2"),
        }),
    )
    inlines = [StaffProfileInline]


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "is_available", "average_rating", "recommendation_score", "total_reviews"]
    list_filter = ["is_available"]
    readonly_fields = ["average_rating", "total_reviews", "recommendation_score", "updated_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
