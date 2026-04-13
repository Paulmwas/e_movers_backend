from django.db import models
from django.conf import settings
from customers.models import Customer
from fleet.models import Truck


class Job(models.Model):
    """
    Central model for a moving job.

    Status machine:
      pending   -> assigned  (staff + trucks allocated)
      assigned  -> in_progress (job started by supervisor)
      in_progress -> completed  (job done, reviews unlocked)
      Any non-completed state -> cancelled

    Only completed jobs unlock billing generation and staff reviews.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class MoveSizeCategory(models.TextChoices):
        STUDIO = "studio", "Studio"
        ONE_BED = "one_bedroom", "1 Bedroom"
        TWO_BED = "two_bedroom", "2 Bedroom"
        THREE_BED = "three_bedroom", "3 Bedroom"
        OFFICE_SMALL = "office_small", "Small Office"
        OFFICE_LARGE = "office_large", "Large Office"

    # Core fields
    title = models.CharField(max_length=200)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="jobs"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    move_size = models.CharField(
        max_length=20, choices=MoveSizeCategory.choices
    )

    # Locations
    pickup_address = models.TextField()
    dropoff_address = models.TextField()
    estimated_distance_km = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )

    # Scheduling
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Requirements hint — actual assignment tracked in JobAssignment / JobTruck
    requested_staff_count = models.PositiveSmallIntegerField(default=10)
    requested_truck_count = models.PositiveSmallIntegerField(default=1)

    # Application flow controls
    application_deadline = models.DateTimeField(
        null=True, blank=True,
        help_text="After this datetime, new applications are rejected."
    )
    max_applicants = models.PositiveSmallIntegerField(
        default=20,
        help_text="Maximum number of APPLIED applications allowed before the slot closes."
    )

    # Attendance PIN — generated on the morning of the move by admin
    attendance_pin = models.CharField(
        max_length=6, blank=True,
        help_text="6-digit PIN staff use to confirm attendance on moving day."
    )

    # Admin notes
    notes = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_date", "-created_at"]
        verbose_name = "Job"
        verbose_name_plural = "Jobs"

    def __str__(self):
        return f"[{self.status.upper()}] {self.title} — {self.customer}"

    @property
    def is_unassigned(self):
        """True when job is PENDING with no staff or truck assignments yet."""
        return (
            self.status == self.Status.PENDING
            and not self.assignments.exists()
        )

    @property
    def supervisor(self):
        """Return the User object of the supervisor assigned to this job, or None."""
        assignment = self.assignments.filter(role=JobAssignment.Role.SUPERVISOR).first()
        return assignment.staff if assignment else None

    @property
    def assigned_staff_count(self):
        return self.assignments.count()

    @property
    def assigned_truck_count(self):
        return self.job_trucks.count()


class JobAssignment(models.Model):
    """
    Links a staff member to a job.
    One SUPERVISOR per job — enforced at the service layer.
    Up to requested_staff_count MOVERs.
    """

    class Role(models.TextChoices):
        SUPERVISOR = "supervisor", "Supervisor"
        MOVER = "mover", "Mover"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="assignments")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="job_assignments",
        limit_choices_to={"role": "mover-staff"},
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MOVER)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="made_assignments",
    )

    class Meta:
        unique_together = [("job", "staff")]
        verbose_name = "Job Assignment"
        verbose_name_plural = "Job Assignments"

    def __str__(self):
        return f"{self.staff.get_full_name()} on {self.job.title} ({self.role})"


class JobTruck(models.Model):
    """Links a truck to a job."""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="job_trucks")
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="job_trucks")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="truck_assignments",
    )

    class Meta:
        unique_together = [("job", "truck")]
        verbose_name = "Job Truck"
        verbose_name_plural = "Job Trucks"

    def __str__(self):
        return f"{self.truck.plate_number} on {self.job.title}"


class JobApplication(models.Model):
    """
    A staff member's application for a pending job.

    Business rules (enforced at service layer):
      - Job must be PENDING.
      - Deadline must not have passed (if set).
      - Max applicant cap must not be reached.
      - One application per (job, staff) pair.
      - Staff must be active.

    Lifecycle:
      applied → approved  (admin approves and creates JobAssignment)
      applied → rejected  (admin approves others; remaining auto-rejected)
      applied → withdrawn (staff self-withdraws before admin review)
    """

    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_applications",
        limit_choices_to={"role": "mover-staff"},
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.APPLIED
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )
    note = models.TextField(blank=True, help_text="Admin note on approval or rejection.")

    class Meta:
        unique_together = [("job", "staff")]
        ordering = ["-applied_at"]
        verbose_name = "Job Application"
        verbose_name_plural = "Job Applications"

    def __str__(self):
        return (
            f"{self.staff.get_full_name()} → {self.job.title} [{self.status.upper()}]"
        )
