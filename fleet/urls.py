from django.urls import path
from . import views

urlpatterns = [
    path("", views.TruckListCreateView.as_view(), name="truck_list_create"),
    path("available/", views.AvailableTrucksView.as_view(), name="available_trucks"),
    path("<int:pk>/", views.TruckDetailView.as_view(), name="truck_detail"),
]
