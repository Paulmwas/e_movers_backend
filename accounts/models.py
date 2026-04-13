from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "mover-admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "mover-admin", "Mover Admin"
        STAFF = "mover-staff", "Mover Staff"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "role"]

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_mover_staff(self):
        return self.role == self.Role.STAFF


class StaffProfile(models.Model):
    """
    Extended profile for mover-staff users.
    Auto-created via signal when a staff User is saved.
    Tracks performance metrics that drive auto-allocation priority:
      - average_rating: mean of all reviews received (0-5)
      - recommendation_score: 0.200 to 1.000 (higher = auto-assigned more often)
      - is_available: False while staff is on an active job
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        limit_choices_to={"role": User.Role.STAFF},
    )
    is_available = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    # Drives auto-allocation ordering. Formula: (avg_rating / 5.0) * 0.8 + 0.2
    # Minimum score 0.200 (worst), maximum 1.000 (best), default 1.000 (no reviews yet)
    recommendation_score = models.DecimalField(
        max_digits=4, decimal_places=3, default=1.000
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Profile"
        verbose_name_plural = "Staff Profiles"

    def __str__(self):
        return f"Profile: {self.user.get_full_name()} | Score: {self.recommendation_score}"

    def recalculate_scores(self):
        """
        Recompute average_rating and recommendation_score from all reviews.
        Called automatically via signal after every new StaffReview is saved.
        Score formula keeps minimum at 0.200 so even poorly-reviewed staff
        still have a small chance of being assigned when no one else is available.
        """
        from django.db.models import Avg
        # Lazy import to avoid circular dependency with reviews app
        from reviews.models import StaffReview

        reviews = StaffReview.objects.filter(reviewee=self.user)
        count = reviews.count()

        if count == 0:
            self.average_rating = 0.00
            self.total_reviews = 0
            self.recommendation_score = 1.000  # Fresh staff get full score
        else:
            avg = reviews.aggregate(avg=Avg("rating"))["avg"] or 0
            self.average_rating = round(avg, 2)
            self.total_reviews = count
            self.recommendation_score = round((float(avg) / 5.0) * 0.8 + 0.2, 3)

        self.save(update_fields=[
            "average_rating", "total_reviews", "recommendation_score", "updated_at"
        ])
