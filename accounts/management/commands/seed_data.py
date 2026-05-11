"""
management command: seed_data
==============================
Populates the database with realistic development/demo data.

Usage:
    python manage.py seed_data              # seed everything
    python manage.py seed_data --flush      # wipe all app data first, then seed
    python manage.py seed_data --jobs-only  # only seed jobs (accounts + customers + fleet must exist)

What gets created:
    - 1 admin user            admin@emovers.co.ke / Admin1234!
    - 20 staff users          staff01@emovers.co.ke ... staff20@emovers.co.ke / Staff1234!
    - 15 customers
    - 8 trucks (various types)
    - Jobs in various states:
        - 3 pending (unassigned) — appear in unassigned jobs alert
        - 3 pending with applications — ready for admin to approve or auto-allocate
        - 2 assigned (auto-allocated)
        - 1 in_progress
        - 3 completed with invoices, payments, and reviews
        - 1 cancelled
"""

import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, timedelta


class Command(BaseCommand):
    help = "Seed the database with realistic development data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing app data before seeding.",
        )
        parser.add_argument(
            "--jobs-only",
            action="store_true",
            help="Only seed jobs. Requires accounts, customers, and fleet to already exist.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        if options["jobs_only"]:
            self._seed_jobs_only()
        else:
            self._seed_all()

        self.stdout.write(self.style.SUCCESS("\nSeeding complete."))
        self.stdout.write(
            "\nAdmin login:\n"
            "  Email   : admin@emovers.co.ke\n"
            "  Password: Admin1234!\n"
            "\nStaff login (any of 20):\n"
            "  Email   : staff01@emovers.co.ke ... staff20@emovers.co.ke\n"
            "  Password: Staff1234!\n"
        )

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def _flush(self):
        from reviews.models import StaffReview
        from billing.models import Payment, Invoice, PaymentDisbursement
        from jobs.models import JobTruck, JobAssignment, JobApplication, Job
        from customers.models import Customer
        from fleet.models import Truck
        from accounts.models import User, StaffProfile

        self.stdout.write("Flushing existing data...")
        StaffReview.objects.all().delete()
        PaymentDisbursement.objects.all().delete()
        Payment.objects.all().delete()
        Invoice.objects.all().delete()
        JobTruck.objects.all().delete()
        JobAssignment.objects.all().delete()
        JobApplication.objects.all().delete()
        Job.objects.all().delete()
        Customer.objects.all().delete()
        Truck.objects.all().delete()
        User.objects.all().delete()
        self.stdout.write(self.style.WARNING("  All data flushed."))

    # ------------------------------------------------------------------
    # Full seed
    # ------------------------------------------------------------------

    @transaction.atomic
    def _seed_all(self):
        admin = self._seed_admin()
        staff_list = self._seed_staff()
        customers = self._seed_customers(admin)
        trucks = self._seed_trucks(admin)
        self._seed_jobs(admin, staff_list, customers, trucks)

    @transaction.atomic
    def _seed_jobs_only(self):
        from accounts.models import User
        from customers.models import Customer
        from fleet.models import Truck

        admin = User.objects.filter(role="mover-admin").first()
        if not admin:
            self.stderr.write("No admin user found. Run seed_data without --jobs-only first.")
            return

        staff_list = list(User.objects.filter(role="mover-staff", is_active=True))
        customers = list(Customer.objects.all())
        trucks = list(Truck.objects.all())

        if not staff_list or not customers or not trucks:
            self.stderr.write("Missing staff, customers, or trucks. Run full seed first.")
            return

        self._seed_jobs(admin, staff_list, customers, trucks)

    # ------------------------------------------------------------------
    # Individual seeders
    # ------------------------------------------------------------------

    def _seed_admin(self):
        from accounts.models import User
        admin, created = User.objects.get_or_create(
            email="admin@emovers.co.ke",
            defaults={
                "first_name": "System",
                "last_name": "Admin",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "phone": "+254700000000",
            },
        )
        if created:
            admin.set_password("Admin1234!")
            admin.save()
            self.stdout.write(f"  Created admin: {admin.email}")
        else:
            self.stdout.write(f"  Admin already exists: {admin.email}")
        return admin

    def _seed_staff(self):
        from accounts.models import User, StaffProfile

        staff_data = [
            ("James",    "Mwangi",    "+254711001001"),
            ("Peter",    "Otieno",    "+254711001002"),
            ("Samuel",   "Kamau",     "+254711001003"),
            ("David",    "Njoroge",   "+254711001004"),
            ("Joseph",   "Waweru",    "+254711001005"),
            ("Michael",  "Kariuki",   "+254711001006"),
            ("George",   "Mugo",      "+254711001007"),
            ("Patrick",  "Gitau",     "+254711001008"),
            ("Francis",  "Maina",     "+254711001009"),
            ("Charles",  "Kipchumba", "+254711001010"),
            ("Daniel",   "Odhiambo",  "+254711001011"),
            ("Stephen",  "Ndung'u",   "+254711001012"),
            ("Robert",   "Kimani",    "+254711001013"),
            ("Thomas",   "Mutua",     "+254711001014"),
            ("William",  "Chesire",   "+254711001015"),
            ("Brian",    "Korir",     "+254711001016"),
            ("Felix",    "Wekesa",    "+254711001017"),
            ("Kevin",    "Mbugua",    "+254711001018"),
            ("Vincent",  "Auma",      "+254711001019"),
            ("Emmanuel", "Ochieng",   "+254711001020"),
        ]

        staff_list = []
        self.stdout.write("Creating staff...")
        for i, (first, last, phone) in enumerate(staff_data, start=1):
            email = f"staff{i:02d}@emovers.co.ke"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "phone": phone,
                    "role": User.Role.STAFF,
                },
            )
            if created:
                user.set_password("Staff1234!")
                user.save()
                StaffProfile.objects.get_or_create(user=user)
                self.stdout.write(f"  Created staff: {email}")
            staff_list.append(user)
        return staff_list

    def _seed_customers(self, admin):
        from customers.models import Customer

        customers_data = [
            ("Alice",    "Wanjiku",   "alice@gmail.com",         "+254720100001", "123 Westlands, Nairobi"),
            ("Brian",    "Omondi",    "brian.o@gmail.com",       "+254720100002", "45 Karen Road, Nairobi"),
            ("Carol",    "Njeri",     "carol.n@gmail.com",       "+254720100003", "78 Ngong Road, Nairobi"),
            ("Dennis",   "Kipchoge",  "dennis.k@gmail.com",      "+254720100004", "12 Lavington, Nairobi"),
            ("Esther",   "Achieng",   "esther.a@gmail.com",      "+254720100005", "90 Kileleshwa, Nairobi"),
            ("Francis",  "Githinji",  "fgithinji@outlook.com",   "+254720100006", "34 Runda, Nairobi"),
            ("Grace",    "Mumbi",     "grace.m@gmail.com",       "+254720100007", "56 Muthaiga, Nairobi"),
            ("Henry",    "Rotich",    "h.rotich@gmail.com",      "+254720100008", "89 Syokimau, Machakos"),
            ("Irene",    "Wambua",    "irene.w@gmail.com",       "+254720100009", "23 Athi River, Machakos"),
            ("John",     "Mwenda",    "jmwenda@gmail.com",       "+254720100010", "67 Thika Road, Nairobi"),
            ("Lucy",     "Wairimu",   "lucy.w@gmail.com",        "+254720100011", "15 Kilimani, Nairobi"),
            ("Moses",    "Cheruiyot", "moses.c@gmail.com",       "+254720100012", "88 Ruiru, Kiambu"),
            ("Nancy",    "Adhiambo",  "nancy.a@outlook.com",     "+254720100013", "32 Embakasi, Nairobi"),
            ("Oliver",   "Mwaniki",   "o.mwaniki@gmail.com",     "+254720100014", "5 Parklands, Nairobi"),
            ("Purity",   "Wangari",   "purity.w@gmail.com",      "+254720100015", "21 South C, Nairobi"),
        ]

        customers = []
        self.stdout.write("Creating customers...")
        for first, last, email, phone, address in customers_data:
            customer, created = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "phone": phone,
                    "address": address,
                    "created_by": admin,
                },
            )
            if created:
                self.stdout.write(f"  Created customer: {email}")
            customers.append(customer)
        return customers

    def _seed_trucks(self, admin):
        from fleet.models import Truck

        trucks_data = [
            ("KDJ 001A", Truck.TruckType.SMALL,        "Isuzu",     "NKR",    2019, "White",  1.0),
            ("KDJ 002B", Truck.TruckType.SMALL,        "Mitsubishi","Canter", 2020, "White",  1.5),
            ("KDJ 003C", Truck.TruckType.MEDIUM,       "Isuzu",     "FRR",    2018, "Blue",   3.0),
            ("KDJ 004D", Truck.TruckType.MEDIUM,       "Hino",      "300",    2021, "White",  3.5),
            ("KDJ 005E", Truck.TruckType.LARGE,        "Isuzu",     "FVZ",    2017, "Yellow", 7.0),
            ("KDJ 006F", Truck.TruckType.EXTRA_LARGE,  "Mercedes",  "Actros", 2022, "White",  10.0),
            ("KDJ 007G", Truck.TruckType.MEDIUM,       "Toyota",    "Dyna",   2020, "Blue",   2.5),
            ("KDJ 008H", Truck.TruckType.LARGE,        "Isuzu",     "FSR",    2019, "White",  5.0),
        ]

        trucks = []
        self.stdout.write("Creating trucks...")
        for plate, ttype, make, model, year, color, capacity in trucks_data:
            truck, created = Truck.objects.get_or_create(
                plate_number=plate,
                defaults={
                    "truck_type": ttype,
                    "make": make,
                    "model": model,
                    "year": year,
                    "color": color,
                    "capacity_tons": Decimal(str(capacity)),
                    "status": Truck.Status.AVAILABLE,
                    "created_by": admin,
                },
            )
            if created:
                self.stdout.write(f"  Created truck: {plate} ({make} {model})")
            trucks.append(truck)
        return trucks

    def _seed_jobs(self, admin, staff_list, customers, trucks):
        self.stdout.write("Creating jobs...")
        self._create_pending_unassigned_jobs(admin, customers)
        self._create_pending_with_applications(admin, staff_list, customers)
        self._create_assigned_jobs(admin, staff_list, customers, trucks)
        self._create_in_progress_job(admin, staff_list, customers, trucks)
        self._create_completed_jobs(admin, staff_list, customers, trucks)
        self._create_cancelled_job(admin, staff_list, customers, trucks)

    # ------------------------------------------------------------------
    # Job scenarios
    # ------------------------------------------------------------------

    def _create_pending_unassigned_jobs(self, admin, customers):
        """
        3 PENDING jobs with NO assignments and NO applications.
        These appear in the unassigned jobs alert on the dashboard.
        """
        from jobs.models import Job

        scenarios = [
            {
                "title": "Wanjiku Studio Move — Westlands to Karen",
                "customer": customers[0],
                "move_size": Job.MoveSizeCategory.STUDIO,
                "pickup_address": "123 Westlands, Nairobi",
                "dropoff_address": "45 Karen Road, Nairobi",
                "estimated_distance_km": Decimal("18.5"),
                "scheduled_date": date.today() + timedelta(days=3),
                "notes": "Client has fragile glassware. Handle with care.",
                "requested_staff_count": 4,
                "requested_truck_count": 1,
            },
            {
                "title": "Rotich 3-Bedroom Move — Syokimau to Muthaiga",
                "customer": customers[7],
                "move_size": Job.MoveSizeCategory.THREE_BED,
                "pickup_address": "89 Syokimau, Machakos",
                "dropoff_address": "56 Muthaiga, Nairobi",
                "estimated_distance_km": Decimal("32.0"),
                "scheduled_date": date.today() + timedelta(days=5),
                "notes": "Large piano included. Needs special handling.",
                "requested_staff_count": 8,
                "requested_truck_count": 2,
            },
            {
                "title": "Wairimu 2-Bedroom Move — Kilimani to Parklands",
                "customer": customers[10],
                "move_size": Job.MoveSizeCategory.TWO_BED,
                "pickup_address": "15 Kilimani, Nairobi",
                "dropoff_address": "5 Parklands, Nairobi",
                "estimated_distance_km": Decimal("9.0"),
                "scheduled_date": date.today() + timedelta(days=6),
                "notes": "New customer. Please confirm 1 hour before arrival.",
                "requested_staff_count": 5,
                "requested_truck_count": 1,
            },
        ]
        for data in scenarios:
            job, created = self._get_or_create_job(data, admin)
            if created:
                self.stdout.write(f"  Created PENDING (unassigned, no applications): {job.title}")

    def _create_pending_with_applications(self, admin, staff_list, customers):
        """
        3 PENDING jobs that already have staff applications (submitted via public form).
        Admin can approve or auto-allocate from here.
        """
        from jobs.models import Job, JobApplication

        scenarios = [
            {
                "job_data": {
                    "title": "Cheruiyot 1-Bedroom Move — Ruiru to Thika Road",
                    "customer": customers[11],
                    "move_size": Job.MoveSizeCategory.ONE_BED,
                    "pickup_address": "88 Ruiru, Kiambu",
                    "dropoff_address": "67 Thika Road, Nairobi",
                    "estimated_distance_km": Decimal("14.0"),
                    "scheduled_date": date.today() + timedelta(days=4),
                    "notes": "Small move. 2 staff sufficient.",
                    "requested_staff_count": 3,
                    "requested_truck_count": 1,
                    "max_applicants": 10,
                },
                # These staff have confirmed availability via the public form
                "applicant_idxs": [0, 1, 2, 3, 5],
            },
            {
                "job_data": {
                    "title": "Adhiambo Office Move — Embakasi to CBD",
                    "customer": customers[12],
                    "move_size": Job.MoveSizeCategory.OFFICE_SMALL,
                    "pickup_address": "32 Embakasi, Nairobi",
                    "dropoff_address": "Kenyatta Avenue, CBD, Nairobi",
                    "estimated_distance_km": Decimal("20.0"),
                    "scheduled_date": date.today() + timedelta(days=7),
                    "notes": "Office equipment. Computers need special packing.",
                    "requested_staff_count": 6,
                    "requested_truck_count": 1,
                    "max_applicants": 15,
                },
                "applicant_idxs": [6, 7, 8, 9, 10, 11, 12],
            },
            {
                "job_data": {
                    "title": "Wangari 3-Bedroom Move — South C to Karen",
                    "customer": customers[14],
                    "move_size": Job.MoveSizeCategory.THREE_BED,
                    "pickup_address": "21 South C, Nairobi",
                    "dropoff_address": "45 Karen Road, Nairobi",
                    "estimated_distance_km": Decimal("15.0"),
                    "scheduled_date": date.today() + timedelta(days=8),
                    "notes": "High value items. Extra care required.",
                    "special_instructions": "Antique furniture — do not stack.",
                    "requested_staff_count": 8,
                    "requested_truck_count": 2,
                    "max_applicants": 20,
                },
                "applicant_idxs": [13, 14, 15, 16, 17, 18, 19, 0, 1],
            },
        ]

        for scenario in scenarios:
            data = scenario["job_data"]
            job, created = self._get_or_create_job(data, admin)
            if not created:
                continue

            # Simulate staff submitting availability via the public form
            for idx in scenario["applicant_idxs"]:
                staff = staff_list[idx]
                try:
                    JobApplication.objects.get_or_create(
                        job=job,
                        staff=staff,
                        defaults={"status": JobApplication.Status.APPLIED},
                    )
                except Exception:
                    pass

            applicant_count = job.applications.filter(
                status=JobApplication.Status.APPLIED
            ).count()
            self.stdout.write(
                f"  Created PENDING (with {applicant_count} applications): {job.title}"
            )

    def _create_assigned_jobs(self, admin, staff_list, customers, trucks):
        """
        2 ASSIGNED jobs with full staff + truck allocation (auto-allocated).
        """
        from jobs.models import Job, JobAssignment, JobTruck
        from accounts.models import StaffProfile

        scenarios = [
            {
                "title": "Omondi 2-Bedroom Move — Karen to Lavington",
                "customer": customers[1],
                "move_size": Job.MoveSizeCategory.TWO_BED,
                "pickup_address": "45 Karen Road, Nairobi",
                "dropoff_address": "12 Lavington, Nairobi",
                "estimated_distance_km": Decimal("12.0"),
                "scheduled_date": date.today() + timedelta(days=1),
                "requested_staff_count": 6,
                "requested_truck_count": 1,
            },
            {
                "title": "Githinji Office Move — CBD to Runda",
                "customer": customers[5],
                "move_size": Job.MoveSizeCategory.OFFICE_SMALL,
                "pickup_address": "Kenyatta Avenue, CBD, Nairobi",
                "dropoff_address": "34 Runda, Nairobi",
                "estimated_distance_km": Decimal("8.0"),
                "scheduled_date": date.today() + timedelta(days=2),
                "requested_staff_count": 5,
                "requested_truck_count": 1,
            },
        ]

        # Use staff indices 0-11 for these two jobs (6 each)
        available_staff = staff_list[:12]
        available_trucks = trucks[:4]

        for i, data in enumerate(scenarios):
            job, created = self._get_or_create_job(data, admin)
            if not created:
                continue

            supervisor = available_staff[i * 6]
            movers = available_staff[i * 6 + 1: i * 6 + 6]

            JobAssignment.objects.create(
                job=job, staff=supervisor,
                role=JobAssignment.Role.SUPERVISOR, assigned_by=admin,
            )
            JobAssignment.objects.bulk_create([
                JobAssignment(job=job, staff=m, role=JobAssignment.Role.MOVER, assigned_by=admin)
                for m in movers
            ])
            StaffProfile.objects.filter(
                user__in=[supervisor] + movers
            ).update(is_available=False)

            truck = available_trucks[i]
            JobTruck.objects.create(job=job, truck=truck, assigned_by=admin)
            from fleet.models import Truck
            Truck.objects.filter(pk=truck.pk).update(status=Truck.Status.ON_JOB)

            job.status = Job.Status.ASSIGNED
            job.save(update_fields=["status"])
            self.stdout.write(f"  Created ASSIGNED: {job.title}")

    def _create_in_progress_job(self, admin, staff_list, customers, trucks):
        """1 IN_PROGRESS job — currently being executed."""
        from jobs.models import Job, JobAssignment, JobTruck
        from accounts.models import StaffProfile
        from fleet.models import Truck as TruckModel

        data = {
            "title": "Mumbi 1-Bedroom Move — Kileleshwa to Ngong Road",
            "customer": customers[6],
            "move_size": Job.MoveSizeCategory.ONE_BED,
            "pickup_address": "90 Kileleshwa, Nairobi",
            "dropoff_address": "78 Ngong Road, Nairobi",
            "estimated_distance_km": Decimal("6.5"),
            "scheduled_date": date.today(),
            "requested_staff_count": 3,
            "requested_truck_count": 1,
        }
        job, created = self._get_or_create_job(data, admin)
        if not created:
            return

        supervisor = staff_list[12]
        movers = staff_list[13:15]

        JobAssignment.objects.create(
            job=job, staff=supervisor,
            role=JobAssignment.Role.SUPERVISOR, assigned_by=admin,
        )
        JobAssignment.objects.bulk_create([
            JobAssignment(job=job, staff=m, role=JobAssignment.Role.MOVER, assigned_by=admin)
            for m in movers
        ])
        StaffProfile.objects.filter(
            user__in=[supervisor] + movers
        ).update(is_available=False)

        truck = trucks[4]
        JobTruck.objects.create(job=job, truck=truck, assigned_by=admin)
        TruckModel.objects.filter(pk=truck.pk).update(status=TruckModel.Status.ON_JOB)

        job.status = Job.Status.IN_PROGRESS
        job.started_at = timezone.now() - timedelta(hours=2)
        job.save(update_fields=["status", "started_at"])
        self.stdout.write(f"  Created IN_PROGRESS: {job.title}")

    def _create_completed_jobs(self, admin, staff_list, customers, trucks):
        """
        3 COMPLETED jobs with invoices, payments, and reviews.
        These demonstrate the full end-to-end flow and show review scores
        affecting recommendation_score for auto-allocation.
        """
        from jobs.models import Job, JobAssignment, JobTruck
        from billing.services import generate_invoice, simulate_payment
        from billing.models import Payment
        from reviews.services import create_review
        from reviews.models import StaffReview

        scenarios = [
            {
                "job_data": {
                    "title": "Achieng 2-Bedroom Move — Kileleshwa to Westlands",
                    "customer": customers[4],
                    "move_size": Job.MoveSizeCategory.TWO_BED,
                    "pickup_address": "90 Kileleshwa, Nairobi",
                    "dropoff_address": "123 Westlands, Nairobi",
                    "estimated_distance_km": Decimal("5.0"),
                    "scheduled_date": date.today() - timedelta(days=3),
                },
                "supervisor_idx": 0,
                "mover_idxs": [1, 2, 3],
                "truck_idx": 2,
                "payment_amount": None,
                "payment_method": Payment.Method.MPESA,
                "reviews": [
                    (1, StaffReview.Category.OVERALL,       5, "Excellent mover, very reliable."),
                    (1, StaffReview.Category.PUNCTUALITY,   5, "Always on time."),
                    (2, StaffReview.Category.OVERALL,       4, "Good worker."),
                    (2, StaffReview.Category.TEAMWORK,      4, "Works well with the team."),
                    (3, StaffReview.Category.OVERALL,       3, "Average performance."),
                    (3, StaffReview.Category.CARE_OF_GOODS, 3, "Could be more careful."),
                ],
            },
            {
                "job_data": {
                    "title": "Mwenda Large Office Move — CBD to Thika Road",
                    "customer": customers[9],
                    "move_size": Job.MoveSizeCategory.OFFICE_LARGE,
                    "pickup_address": "67 Haile Selassie Ave, CBD, Nairobi",
                    "dropoff_address": "67 Thika Road, Nairobi",
                    "estimated_distance_km": Decimal("15.0"),
                    "scheduled_date": date.today() - timedelta(days=7),
                },
                "supervisor_idx": 4,
                "mover_idxs": [5, 6, 7, 8],
                "truck_idx": 5,
                "payment_amount": None,
                "payment_method": Payment.Method.BANK_TRANSFER,
                "reviews": [
                    (5, StaffReview.Category.OVERALL,          5, "Outstanding work on the large office move."),
                    (5, StaffReview.Category.COMMUNICATION,    5, "Excellent communication throughout."),
                    (6, StaffReview.Category.OVERALL,          4, "Very good worker."),
                    (7, StaffReview.Category.OVERALL,          2, "Was slow and needed constant supervision."),
                    (7, StaffReview.Category.PHYSICAL_FITNESS, 1, "Struggled with heavy items."),
                    (8, StaffReview.Category.OVERALL,          4, "Good effort."),
                ],
            },
            {
                "job_data": {
                    "title": "Mwaniki 3-Bedroom Move — Parklands to Lavington",
                    "customer": customers[13],
                    "move_size": Job.MoveSizeCategory.THREE_BED,
                    "pickup_address": "5 Parklands, Nairobi",
                    "dropoff_address": "12 Lavington, Nairobi",
                    "estimated_distance_km": Decimal("11.0"),
                    "scheduled_date": date.today() - timedelta(days=14),
                },
                "supervisor_idx": 15,
                "mover_idxs": [16, 17, 18, 19],
                "truck_idx": 6,
                "payment_amount": None,
                "payment_method": Payment.Method.CASH,
                "reviews": [
                    (16, StaffReview.Category.OVERALL,       5, "Excellent team player."),
                    (16, StaffReview.Category.PUNCTUALITY,   4, "Arrived 10 minutes early."),
                    (17, StaffReview.Category.OVERALL,       5, "Best mover I've worked with."),
                    (17, StaffReview.Category.CARE_OF_GOODS, 5, "Zero damage to any items."),
                    (18, StaffReview.Category.OVERALL,       3, "Decent but slow."),
                    (19, StaffReview.Category.OVERALL,       4, "Good attitude throughout."),
                    (19, StaffReview.Category.TEAMWORK,      5, "Kept the team motivated."),
                ],
            },
        ]

        for scenario in scenarios:
            data = scenario["job_data"]
            job, created = self._get_or_create_job(data, admin)
            if not created:
                continue

            sup_idx = scenario["supervisor_idx"]
            supervisor = staff_list[sup_idx]
            movers = [staff_list[i] for i in scenario["mover_idxs"]]
            truck = trucks[scenario["truck_idx"]]

            JobAssignment.objects.create(
                job=job, staff=supervisor,
                role=JobAssignment.Role.SUPERVISOR, assigned_by=admin,
            )
            JobAssignment.objects.bulk_create([
                JobAssignment(job=job, staff=m, role=JobAssignment.Role.MOVER, assigned_by=admin)
                for m in movers
            ])
            JobTruck.objects.create(job=job, truck=truck, assigned_by=admin)

            job.status = Job.Status.COMPLETED
            job.started_at = timezone.now() - timedelta(days=abs(data["scheduled_date"].day), hours=6)
            job.completed_at = job.started_at + timedelta(hours=4)
            job.save(update_fields=["status", "started_at", "completed_at"])

            invoice = generate_invoice(
                job=job,
                created_by=admin,
                due_date=date.today() + timedelta(days=7),
            )

            pay_amount = scenario["payment_amount"] or invoice.total_amount
            simulate_payment(
                invoice=invoice,
                amount=pay_amount,
                method=scenario["payment_method"],
                recorded_by=admin,
            )

            for mover_local_idx, category, rating, comment in scenario["reviews"]:
                all_mover_idxs = scenario["mover_idxs"]
                # mover_local_idx is 1-based index into the mover_idxs list
                list_idx = mover_local_idx - 1
                if list_idx < 0 or list_idx >= len(all_mover_idxs):
                    continue
                reviewee = staff_list[all_mover_idxs[list_idx]]
                try:
                    create_review(
                        job=job,
                        reviewer=supervisor,
                        reviewee=reviewee,
                        category=category,
                        rating=rating,
                        comment=comment,
                    )
                except Exception:
                    pass  # Skip duplicates on re-run

            self.stdout.write(
                f"  Created COMPLETED (invoice + payment + reviews): {job.title}"
            )

    def _create_cancelled_job(self, admin, staff_list, customers, trucks):
        """1 CANCELLED job — customer changed plans."""
        from jobs.models import Job, JobApplication

        data = {
            "title": "Njeri Studio Move — Ngong Road to Karen (Cancelled)",
            "customer": customers[2],
            "move_size": Job.MoveSizeCategory.STUDIO,
            "pickup_address": "78 Ngong Road, Nairobi",
            "dropoff_address": "45 Karen Road, Nairobi",
            "estimated_distance_km": Decimal("8.0"),
            "scheduled_date": date.today() - timedelta(days=2),
            "notes": "Customer cancelled — decided to delay the move.",
            "requested_staff_count": 2,
            "requested_truck_count": 1,
        }
        job, created = self._get_or_create_job(data, admin)
        if not created:
            return

        # A few staff had already applied before the cancellation
        for idx in [3, 4]:
            try:
                app, _ = JobApplication.objects.get_or_create(
                    job=job, staff=staff_list[idx],
                    defaults={"status": JobApplication.Status.APPLIED},
                )
                # Mark them as withdrawn/rejected due to cancellation
                app.status = JobApplication.Status.REJECTED
                app.reviewed_by = admin
                app.reviewed_at = timezone.now()
                app.note = "Job cancelled by customer."
                app.save(update_fields=["status", "reviewed_by", "reviewed_at", "note"])
            except Exception:
                pass

        job.status = Job.Status.CANCELLED
        job.save(update_fields=["status"])
        self.stdout.write(f"  Created CANCELLED: {job.title}")

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    def _get_or_create_job(self, data, admin):
        from jobs.models import Job
        existing = Job.objects.filter(title=data["title"]).first()
        if existing:
            return existing, False
        job = Job.objects.create(created_by=admin, **data)
        return job, True
