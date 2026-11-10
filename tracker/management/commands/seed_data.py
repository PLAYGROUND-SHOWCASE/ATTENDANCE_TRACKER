import random
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from tracker.models import (
    Department, OfficeLocation, RouterConfig, EmployeeProfile, 
    Attendance, SimulationState, AuditLog, LaptopActivityLog, OutsideOfficeLog,
    Company, Branch, Division, CostCenter, Team, Project, Sprint, Issue,
    EmployeeSkill, Expense, Notification, CustomWidget
)

class Command(BaseCommand):
    help = 'Seeds database with realistic enterprise departments, office locations, routers, users, projects, and logs.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Clearing existing data...')
        
        # Delete new models
        CustomWidget.objects.all().delete()
        Notification.objects.all().delete()
        Expense.objects.all().delete()
        EmployeeSkill.objects.all().delete()
        Issue.objects.all().delete()
        Sprint.objects.all().delete()
        Team.objects.all().delete()
        Project.objects.all().delete()
        CostCenter.objects.all().delete()
        Division.objects.all().delete()
        Branch.objects.all().delete()
        Company.objects.all().delete()

        # Delete existing models
        OutsideOfficeLog.objects.all().delete()
        LaptopActivityLog.objects.all().delete()
        Attendance.objects.all().delete()
        SimulationState.objects.all().delete()
        RouterConfig.objects.all().delete()
        EmployeeProfile.objects.all().delete()
        OfficeLocation.objects.all().delete()
        Department.objects.all().delete()
        
        User.objects.filter(is_superuser=False).delete()
        
        self.stdout.write('Seeding core infrastructure...')
        # 1. Company & Branches
        company = Company.objects.create(
            name="Scholigence Technology Corp",
            logo_url="https://images.unsplash.com/photo-1599305445671-ac291c95aba9?w=150",
            description="Enterprise tracking software development & consulting."
        )
        
        b_hq = Branch.objects.create(
            company=company,
            name="Boston HQ",
            address="45 Milk St, Boston, MA",
            city="Boston"
        )
        
        b_london = Branch.objects.create(
            company=company,
            name="London Branch",
            address="100 Victoria St, London",
            city="London"
        )
        
        # 2. Departments & Divisions
        eng = Department.objects.create(name="Engineering", description="Software development & operations")
        hr = Department.objects.create(name="Human Resources", description="Talent acquisition and benefits")
        sales = Department.objects.create(name="Sales", description="Business development and sales operations")
        
        Division.objects.create(department=eng, name="Core Platform", description="Main SaaS framework")
        Division.objects.create(department=eng, name="Cloud Services", description="AWS/GCP integration")
        Division.objects.create(department=hr, name="Talent Acquisition", description="Recruiting talent")
        
        # 3. Office Locations & WiFi Infrastructure
        hq_loc = OfficeLocation.objects.create(
            name="Scholigence 4th Floor",
            address="Scholigence Office, 4th Floor",
            latitude=12.9716,
            longitude=77.5946,
            geofence_radius=100
        )
        
        RouterConfig.objects.create(
            office=hq_loc,
            name="Cisco HQ-Router-01",
            ssid="Enterprise-WiFi-01",
            gateway_ip="192.168.1.1",
            mac_address="00:1A:2B:3C:4D:5E",
            is_online=True
        )

        # 4. Cost Centers
        cc_rd = CostCenter.objects.create(code="RD-2026", name="Research & Development", budget=150000.0)
        cc_ops = CostCenter.objects.create(code="OPS-2026", name="Operations", budget=80000.0)

        self.stdout.write('Seeding employee accounts...')
        # 5. Create Admin / Managers
        admin_user, _ = User.objects.get_or_create(username='admin')
        admin_user.set_password('admin')
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()
            
        admin_profile, _ = EmployeeProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'employee_id': 'EMP-0001',
                'photo_url': 'https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=150',
                'designation': 'HR Director',
                'office_location': hq_loc,
                'branch': b_hq,
                'department': hr,
                'role': 'ADMIN',
                'current_status': 'WORKING',
                'assigned_laptop_mac': 'AA:BB:CC:DD:EE:01'
            }
        )
        SimulationState.objects.get_or_create(employee=admin_profile)

        # Developer accounts
        dev_user = User.objects.create_user(username='developer', password='password123', first_name='John', last_name='Doe', email='dev@scholigence.com')
        dev_profile = EmployeeProfile.objects.create(
            user=dev_user,
            employee_id='EMP-0002',
            photo_url='https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150',
            designation='Lead Developer',
            office_location=hq_loc,
            branch=b_hq,
            department=eng,
            role='TEAM_LEAD',
            current_status='WORKING',
            assigned_laptop_mac='AA:BB:CC:DD:EE:02'
        )
        SimulationState.objects.create(employee=dev_profile)

        # Seed Skills
        EmployeeSkill.objects.create(employee=dev_profile, skill_name="Django / Python", proficiency="EXPERT")
        EmployeeSkill.objects.create(employee=dev_profile, skill_name="React / JS", proficiency="INTERMEDIATE")
        EmployeeSkill.objects.create(employee=admin_profile, skill_name="Talent Sourcing", proficiency="EXPERT")

        # 6. Custom Teams
        team_titan = Team.objects.create(
            name="Titan Sprints",
            department=eng,
            lead=dev_profile,
            description="Core Platform engineering sprint team."
        )
        team_titan.members.add(dev_profile, admin_profile)

        self.stdout.write('Seeding project boards & sprint logs...')
        # 7. Projects & Sprints & Issues
        proj_jira = Project.objects.create(
            name="Jira Platform Revamp",
            key="JIRA",
            description="SaaS Project Management board revamp project.",
            category="Software",
            priority="CRITICAL",
            status="ACTIVE",
            template_name="SOFTWARE",
            budget=95000.0,
            created_by=admin_user,
            cost_center=cc_rd,
            start_date=timezone.localdate() - timezone.timedelta(days=10),
            end_date=timezone.localdate() + timezone.timedelta(days=80)
        )
        
        s1 = Sprint.objects.create(
            project=proj_jira,
            name="Sprint 1: Bootstrap Kanban",
            start_date=timezone.localdate() - timezone.timedelta(days=10),
            end_date=timezone.localdate() + timezone.timedelta(days=4),
            status="ACTIVE"
        )
        
        # Issues
        Issue.objects.create(
            project=proj_jira, sprint=s1, title="Bootstrap glassmorphism UI layout",
            description="Apply premium dark variables to project views.",
            issue_type="STORY", status="IN_PROGRESS", priority="HIGH",
            assignee=dev_profile, reporter=admin_profile, story_points=5,
            due_date=timezone.localdate() + timezone.timedelta(days=2)
        )
        
        Issue.objects.create(
            project=proj_jira, sprint=s1, title="MFA login token validation drop",
            description="Resolve login crash when scanned QR doesn't save to cookie.",
            issue_type="BUG", status="TODO", priority="CRITICAL",
            assignee=dev_profile, reporter=admin_profile, story_points=3,
            due_date=timezone.localdate() + timezone.timedelta(days=1)
        )

        Issue.objects.create(
            project=proj_jira, sprint=s1, title="Dynamic timeline Gantt chart components",
            description="Render SVG-based task duration indicators.",
            issue_type="TASK", status="DONE", priority="MEDIUM",
            assignee=dev_profile, reporter=admin_profile, story_points=2,
            due_date=timezone.localdate() - timezone.timedelta(days=2)
        )

        # 8. Expenses
        Expense.objects.create(
            employee=dev_profile,
            project=proj_jira,
            amount=4200.0,
            category="Software License",
            description="Jira Enterprise Developer subscriptions billing",
            status="APPROVED",
            approved_by=admin_profile
        )
        
        Expense.objects.create(
            employee=dev_profile,
            project=proj_jira,
            amount=850.0,
            category="Meals & Entertainment",
            description="Developer kick-off dinner catering claim",
            status="PENDING"
        )

        # 9. Attendance
        Attendance.objects.create(
            employee=dev_profile,
            date=timezone.localdate(),
            check_in=timezone.now() - timezone.timedelta(hours=8),
            check_in_method='MANUAL',
            status='PRESENT'
        )

        # 10. Notifications
        Notification.objects.create(
            user=dev_user,
            message="You have been added to the Titan Sprints team!"
        )

        # 11. Custom widgets settings
        default_widgets = ["WORKLOAD", "DEADLINES", "PERFORMANCE", "CALENDAR", "HEALTH", "ATTENDANCE"]
        for idx, w_type in enumerate(default_widgets):
            CustomWidget.objects.create(user=dev_user, widget_type=w_type, is_enabled=True, order=idx)
            CustomWidget.objects.create(user=admin_user, widget_type=w_type, is_enabled=True, order=idx)

        AuditLog.objects.create(
            action="SYSTEM_INIT",
            details="Enterprise Project Management Monitor seeder ran successfully.",
            ip_address="127.0.0.1"
        )
        
        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
        self.stdout.write(self.style.SUCCESS('Credentials: admin / admin, developer / password123'))
