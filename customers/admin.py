from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        "get_full_name", "email", "phone", "created_by", "created_at"
    ]
    search_fields = ["first_name", "last_name", "email", "phone"]
    readonly_fields = ["created_by", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = "Name"
