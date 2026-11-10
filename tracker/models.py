from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __cloner__(self):
        return self.name

    def __str__(self):
        return self.name

class OfficeLocation(models.Model):
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    geofence_radius = models.IntegerField(default=100, help_text="Radius in meters")

    def __str__(self):
        return self.name

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True, default="https://images.unsplash.com/photo-1599305445671-ac291c95aba9?w=150")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.city}"

class RouterConfig(models.Model):
    office = models.ForeignKey(OfficeLocation, on_delete=models.CASCADE, related_name="routers")
    name = models.CharField(max_length=100)
    ssid = models.CharField(max_length=100)
    gateway_ip = models.GenericIPAddressField(default="192.168.1.1")
    mac_address = models.CharField(max_length=17, blank=True, null=True, help_text="Router hardware MAC address")
    is_online = models.BooleanField(default=True)
    last_ping = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.ssid}) - {self.office.name}"

class EmployeeProfile(models.Model):
    STATUS_CHOICES = [
        ('WORKING', 'Working 🟢'),
        ('IDLE', 'Idle 🟡'),
        ('MEETING', 'Meeting 🔵'),
        ('OUTSIDE', 'Outside Office 🟠'),
        ('OFFLINE', 'Offline 🔴'),
        ('CHECKED_OUT', 'Checked Out ⚫'),
    ]

    EMPLOYMENT_TYPES = [
        ('FULL_TIME', 'Full-time'),
        ('PART_TIME', 'Part-time'),
        ('CONTRACTOR', 'Contractor'),
        ('INTERN', 'Intern'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    employee_id = models.CharField(max_length=20, unique=True)
    photo_url = models.URLField(max_length=500, blank=True, null=True, default="https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=150")
    phone = models.CharField(max_length=20, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    designation = models.CharField(max_length=100)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name="subordinates")
    joining_date = models.DateField(default=timezone.now)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='FULL_TIME')
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    role = models.CharField(max_length=20, choices=[('ADMIN', 'Admin'), ('EXECUTIVE', 'Executive'), ('MANAGER', 'Manager'), ('TEAM_LEAD', 'Team Lead'), ('EMPLOYEE', 'Employee')], default='EMPLOYEE')
    
    # Device bindings
    assigned_laptop_mac = models.CharField(max_length=17, blank=True, null=True, help_text="Format: AA:BB:CC:DD:EE:FF")
    assigned_desktop_mac = models.CharField(max_length=17, blank=True, null=True)
    assigned_phone_mac = models.CharField(max_length=17, blank=True, null=True, help_text="Format: AA:BB:CC:DD:EE:GG")
    wifi_device_id = models.CharField(max_length=50, blank=True, null=True)
    router_authorized = models.BooleanField(default=True)
    
    # Live states
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OFFLINE')
    last_status_change = models.DateTimeField(default=timezone.now)
    last_active_time = models.DateTimeField(default=timezone.now)
    last_seen_ip = models.GenericIPAddressField(blank=True, null=True)
    ip_history = models.TextField(default="[]", help_text="JSON string of recent IPs")
    
    # Shift Settings
    shift_start = models.TimeField(default="09:00:00")
    shift_end = models.TimeField(default="18:00:00")
    
    # Daily cache values (reset by cron/simulation start)
    working_hours_today = models.FloatField(default=0.0, help_text="Total hours in WORKING status today")
    idle_hours_today = models.FloatField(default=0.0, help_text="Total hours in IDLE status today")
    break_hours_today = models.FloatField(default=0.0, help_text="Total hours on break today")
    outside_hours_today = models.FloatField(default=0.0, help_text="Total hours spent outside router today")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.employee_id})"

class Attendance(models.Model):
    METHODS = [
        ('MANUAL', 'Manual Button'),
        ('AUTO_ROUTER', 'Router Auto-Detection'),
        ('LAPTOP_AGENT', 'Laptop Agent Sign-in'),
        ('BROWSER', 'Portal Session Autologin'),
        ('RFID', 'RFID Card Tap'),
        ('FACE', 'Facial Recognition'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(default=timezone.now)
    check_in = models.DateTimeField(default=timezone.now)
    check_out = models.DateTimeField(blank=True, null=True)
    check_in_method = models.CharField(max_length=20, choices=METHODS, default='MANUAL')
    check_out_method = models.CharField(max_length=20, choices=METHODS, blank=True, null=True)
    total_hours = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=[('PRESENT', 'Present'), ('ABSENT', 'Absent'), ('LATE', 'Late')], default='PRESENT')

    class Meta:
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"{self.employee} - {self.date} - {self.status}"

class RouterPresenceLog(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="router_logs")
    router = models.ForeignKey(RouterConfig, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    local_ip = models.GenericIPAddressField()
    signal_strength = models.CharField(max_length=20, choices=[('EXCELLENT', 'Excellent'), ('GOOD', 'Good'), ('FAIR', 'Fair'), ('POOR', 'Poor'), ('DISCONNECTED', 'Disconnected')])
    connection_time = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    duration_minutes = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.employee.user.username} on {self.router.name} - {self.signal_strength}"

class LaptopActivityLog(models.Model):
    STATES = [
        ('ON', 'Powered On'),
        ('OFF', 'Shutdown'),
        ('SLEEP', 'Sleep Mode'),
        ('LOCK', 'Locked Screen'),
        ('UNLOCK', 'Unlocked Screen'),
        ('IDLE', 'Idle (No Inputs)'),
        ('ACTIVE', 'Active Work'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="laptop_logs")
    timestamp = models.DateTimeField(default=timezone.now)
    state = models.CharField(max_length=20, choices=STATES)
    idle_duration_seconds = models.IntegerField(default=0)
    active_application = models.CharField(max_length=255, blank=True, null=True)
    cpu_usage = models.FloatField(default=0.0)
    is_tampered = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee.user.username} Laptop {self.state} at {self.timestamp}"

class OutsideOfficeLog(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="outside_logs")
    out_time = models.DateTimeField(default=timezone.now)
    return_time = models.DateTimeField(blank=True, null=True)
    duration_seconds = models.IntegerField(default=0)
    reason = models.CharField(max_length=255, default="Lunch Break")

    def __str__(self):
        return f"{self.employee.user.username} Outside for {self.duration_seconds}s"

class InternetStatusLog(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="internet_logs")
    offline_start = models.DateTimeField(default=timezone.now)
    online_return = models.DateTimeField(blank=True, null=True)
    duration_seconds = models.IntegerField(default=0)
    auto_checkout_triggered = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee.user.username} Internet Offline for {self.duration_seconds}s"

class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('SICK', 'Sick Leave'),
        ('CASUAL', 'Casual Leave'),
        ('ANNUAL', 'Annual Paid Leave'),
        ('UNPAID', 'Unpaid Leave'),
    ]

    STATUS = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="leaves")
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default='PENDING')
    approved_by = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_leaves")
    applied_on = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.status})"

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    action = models.CharField(max_length=100)
    details = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    def __str__(self):
        return f"{self.timestamp} - {self.action} by {self.user}"

class SimulationState(models.Model):
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE, related_name="sim_state")
    wifi_connected = models.BooleanField(default=True)
    wifi_disconnect_duration = models.IntegerField(default=0) # in minutes
    laptop_state = models.CharField(max_length=20, default="ACTIVE") # ACTIVE, SLEEP, LOCK, SHUTDOWN, ON
    laptop_sleep_duration = models.IntegerField(default=0) # in minutes
    internet_active = models.BooleanField(default=True)
    internet_lost_duration = models.IntegerField(default=0) # in minutes
    browser_open = models.BooleanField(default=True)
    browser_closed_duration = models.IntegerField(default=0) # in minutes
    idle_duration = models.IntegerField(default=0) # in minutes
    
    # Phone & Distance Tracking Simulation
    phone_connected = models.BooleanField(default=True)
    phone_disconnect_duration = models.IntegerField(default=0) # in minutes
    phone_laptop_distance = models.FloatField(default=2.0) # in meters

    def __str__(self):
        return f"SimState for {self.employee}"

class Division(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="divisions")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('department', 'name')

    def __str__(self):
        return f"{self.name} ({self.department.name})"

class CostCenter(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    budget = models.FloatField(default=0.0)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams")
    lead = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="led_teams")
    members = models.ManyToManyField(EmployeeProfile, related_name="custom_teams", blank=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Project(models.Model):
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ARCHIVED', 'Archived'),
        ('COMPLETED', 'Completed'),
    ]
    name = models.CharField(max_length=100, unique=True)
    key = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=50, default="Software")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    template_name = models.CharField(max_length=100, blank=True, null=True)
    budget = models.FloatField(default=0.0)
    cost = models.FloatField(default=0.0)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects")

    def __str__(self):
        return f"{self.name} ({self.key})"

class Sprint(models.Model):
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNED')

    def __str__(self):
        return f"{self.project.key} - {self.name} ({self.status})"

class Issue(models.Model):
    TYPE_CHOICES = [
        ('TASK', 'Task 📋'),
        ('BUG', 'Bug 🐛'),
        ('STORY', 'Story 📖'),
        ('EPIC', 'Epic ⚡'),
    ]
    STATUS_CHOICES = [
        ('BACKLOG', 'Backlog'),
        ('TODO', 'To Do'),
        ('IN_PROGRESS', 'In Progress'),
        ('IN_REVIEW', 'In Review'),
        ('DONE', 'Done'),
    ]
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="issues")
    sprint = models.ForeignKey(Sprint, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    issue_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='TASK')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BACKLOG')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    assignee = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_issues")
    reporter = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="reported_issues")
    story_points = models.IntegerField(default=0)
    due_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.key}-{self.id}: {self.title}"

class EmployeeSkill(models.Model):
    PROFICIENCY_CHOICES = [
        ('BEGINNER', 'Beginner'),
        ('INTERMEDIATE', 'Intermediate'),
        ('EXPERT', 'Expert'),
    ]
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="skills")
    skill_name = models.CharField(max_length=100)
    proficiency = models.CharField(max_length=20, choices=PROFICIENCY_CHOICES, default='INTERMEDIATE')

    class Meta:
        unique_together = ('employee', 'skill_name')

    def __str__(self):
        return f"{self.employee.user.username} - {self.skill_name} ({self.proficiency})"

class Expense(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="expenses")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    amount = models.FloatField(default=0.0)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    approved_by = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_expenses")

    def __str__(self):
        return f"{self.employee.user.username} - {self.category} - {self.amount}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="custom_notifications")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:30]}..."

class CustomWidget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="widgets")
    widget_type = models.CharField(max_length=50)
    is_enabled = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'widget_type')

    def __str__(self):
        return f"{self.user.username} - {self.widget_type} ({self.is_enabled})"
