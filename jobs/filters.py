import django_filters
from .models import Job


class JobFilter(django_filters.FilterSet):
    """
    Advanced filter for the Job list endpoint.

    Supports all these query params simultaneously:
      ?status=pending
      ?move_size=two_bedroom
      ?customer=5
      ?scheduled_date_after=2025-01-01
      ?scheduled_date_before=2025-12-31
      ?created_after=2025-01-01
      ?has_supervisor=true
      ?is_unassigned=true
    """
    scheduled_date_after = django_filters.DateFilter(
        field_name="scheduled_date", lookup_expr="gte",
        label="Scheduled on or after (YYYY-MM-DD)",
    )
    scheduled_date_before = django_filters.DateFilter(
        field_name="scheduled_date", lookup_expr="lte",
        label="Scheduled on or before (YYYY-MM-DD)",
    )
    created_after = django_filters.DateFilter(
        field_name="created_at", lookup_expr="date__gte",
        label="Created on or after (YYYY-MM-DD)",
    )
    created_before = django_filters.DateFilter(
        field_name="created_at", lookup_expr="date__lte",
        label="Created on or before (YYYY-MM-DD)",
    )
    has_supervisor = django_filters.BooleanFilter(
        method="filter_has_supervisor",
        label="Has a supervisor assigned (true/false)",
    )
    is_unassigned = django_filters.BooleanFilter(
        method="filter_is_unassigned",
        label="Unassigned jobs only (pending + no assignments)",
    )

    class Meta:
        model = Job
        fields = ["status", "move_size", "customer"]

    def filter_has_supervisor(self, queryset, name, value):
        from .models import JobAssignment
        supervisor_job_ids = JobAssignment.objects.filter(
            role=JobAssignment.Role.SUPERVISOR
        ).values_list("job_id", flat=True)
        if value:
            return queryset.filter(pk__in=supervisor_job_ids)
        return queryset.exclude(pk__in=supervisor_job_ids)

    def filter_is_unassigned(self, queryset, name, value):
        if value:
            return (
                queryset.filter(status=Job.Status.PENDING)
                .exclude(assignments__isnull=False)
            )
        return queryset
