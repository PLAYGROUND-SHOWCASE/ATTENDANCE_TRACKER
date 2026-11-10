from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from tracker.models import (
    Department, OfficeLocation, EmployeeProfile, Attendance, SimulationState,
    Company, Branch, Division, CostCenter, Team, Project, Sprint, Issue,
    EmployeeSkill, Expense, Notification, CustomWidget
)
from tracker.rules import enforce_checkout_rules


class AttendanceRulesTestCase(TestCase):
    def setUp(self):
        # Setup Core Infrastructure
        self.dept = Department.objects.create(name="QA")
        self.office = OfficeLocation.objects.create(
            name="Boston Office", 
            address="45 Milk St, Boston, MA", 
            latitude=42.3584, 
            longitude=-71.0598
        )
        
        # Setup User & Profile
        self.user = User.objects.create_user(username="test_emp", password="password123")
        self.profile = EmployeeProfile.objects.create(
            user=self.user,
            employee_id="EMP-9999",
            designation="QA Engineer",
            department=self.dept,
            office_location=self.office,
            assigned_laptop_mac="FF:EE:DD:CC:BB:AA"
        )
        
        # Setup Simulation State
        self.sim_state = SimulationState.objects.create(
            employee=self.profile,
            wifi_connected=True,
            laptop_state="ACTIVE",
            internet_active=True,
            browser_open=True
        )

    def test_manual_checkin(self):
        """Verifies manual check-in creates an active attendance record and updates status."""
        today = timezone.localdate()
        self.profile.current_status = 'OFFLINE'
        self.profile.save()
        
        Attendance.objects.create(
            employee=self.profile,
            date=today,
            check_in=timezone.now(),
            check_in_method='MANUAL'
        )
        
        # Run rules engine to align state
        enforce_checkout_rules(self.profile, time_passed_minutes=0)
        
        # Assert status is WORKING
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_status, 'WORKING')
        
        # Assert active attendance exists
        attendance = Attendance.objects.filter(employee=self.profile, date=today, check_out__isnull=True).first()
        self.assertIsNotNone(attendance)

    def test_rule_1_internet_offline_timeout(self):
        """Verifies Rule 1: Internet disconnected for 10 minutes triggers auto checkout."""
        today = timezone.localdate()
        Attendance.objects.create(
            employee=self.profile,
            date=today,
            check_in=timezone.now(),
            check_in_method='MANUAL'
        )
        
        # Drop internet
        self.sim_state.internet_active = False
        self.sim_state.save()
        
        # Simulate 5 minutes passing -> Should NOT check out, status should be OFFLINE
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=5)
        self.assertFalse(checkout_fired)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_status, 'OFFLINE')
        
        # Simulate another 5 minutes passing (Total: 10 mins) -> Should check out
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=5)
        self.assertTrue(checkout_fired)
        
        # Assert attendance is checked out
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_status, 'OFFLINE')
        attendance = Attendance.objects.filter(employee=self.profile, date=today, check_out__isnull=True).first()
        self.assertIsNone(attendance)

    def test_rule_2_wifi_disconnect_timeout(self):
        """Verifies Rule 2: WiFi disconnected for 15 minutes triggers auto checkout."""
        today = timezone.localdate()
        Attendance.objects.create(
            employee=self.profile,
            date=today,
            check_in=timezone.now(),
            check_in_method='MANUAL'
        )
        
        # Disconnect from WiFi
        self.sim_state.wifi_connected = False
        self.sim_state.save()
        
        # Simulate 10 minutes passing -> Should NOT check out, status should be OUTSIDE
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=10)
        self.assertFalse(checkout_fired)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_status, 'OUTSIDE')
        
        # Simulate another 5 minutes passing (Total: 15 mins) -> Should check out
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=5)
        self.assertTrue(checkout_fired)
        
        # Assert attendance is checked out
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_status, 'OFFLINE')
        attendance = Attendance.objects.filter(employee=self.profile, date=today, check_out__isnull=True).first()
        self.assertIsNone(attendance)

    def test_rule_3_laptop_shutdown_immediate(self):
        """Verifies Rule 3: Laptop shutdown triggers immediate checkout."""
        today = timezone.localdate()
        Attendance.objects.create(
            employee=self.profile,
            date=today,
            check_in=timezone.now(),
            check_in_method='MANUAL'
        )
        
        # Set state to OFF (shutdown)
        self.sim_state.laptop_state = 'OFF'
        self.sim_state.save()
        
        # Evaluate rules -> Should trigger immediate checkout
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=0)
        self.assertTrue(checkout_fired)
        
        # Assert checked out
        attendance = Attendance.objects.filter(employee=self.profile, date=today, check_out__isnull=True).first()
        self.assertIsNone(attendance)

    def test_rule_6_idle_timeout(self):
        """Verifies Rule 6: 30 minutes of complete inactivity triggers auto checkout."""
        today = timezone.localdate()
        Attendance.objects.create(
            employee=self.profile,
            date=today,
            check_in=timezone.now(),
            check_in_method='MANUAL'
        )
        
        # Make user idle for 30 minutes
        self.sim_state.laptop_state = 'IDLE'
        self.sim_state.idle_duration = 30
        self.sim_state.save()
        
        # Evaluate rules
        checkout_fired, msg = enforce_checkout_rules(self.profile, time_passed_minutes=0)
        self.assertTrue(checkout_fired)
        
        # Assert checked out
        attendance = Attendance.objects.filter(employee=self.profile, date=today, check_out__isnull=True).first()
        self.assertIsNone(attendance)


class ProjectManagementTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test_admin", password="password")
        self.dept = Department.objects.create(name="Product")
        self.profile = EmployeeProfile.objects.create(
            user=self.user, employee_id="EMP-777", designation="Product Manager", department=self.dept
        )
        self.cc = CostCenter.objects.create(code="PM-2026", name="Product CC", budget=10000.0)
        self.proj = Project.objects.create(
            name="Alpha Platform", key="ALPHA", priority="HIGH", budget=5000.0, created_by=self.user, cost_center=self.cc
        )

    def test_project_cost_accumulation(self):
        self.assertEqual(self.proj.cost, 0.0)
        
        # File and approve an expense
        expense = Expense.objects.create(
            employee=self.profile, project=self.proj, amount=1200.0, category="Licensing", status="PENDING"
        )
        self.assertEqual(self.proj.cost, 0.0)
        
        # Approve expense
        expense.status = 'APPROVED'
        expense.approved_by = self.profile
        expense.save()
        
        self.proj.cost += expense.amount
        self.proj.save()
        self.assertEqual(self.proj.cost, 1200.0)

    def test_issue_creation(self):
        sprint = Sprint.objects.create(
            project=self.proj, name="Sprint 1", start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=14)
        )
        issue = Issue.objects.create(
            project=self.proj, sprint=sprint, title="Fix auth cookie", issue_type="BUG", status="TODO", assignee=self.profile, story_points=3
        )
        self.assertEqual(issue.project, self.proj)
        self.assertEqual(issue.sprint, sprint)
        self.assertEqual(issue.story_points, 3)
