from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from .models import (
    Department, OfficeLocation, EmployeeProfile, Attendance, RouterConfig, LeaveRequest, 
    AuditLog, LaptopActivityLog, OutsideOfficeLog, InternetStatusLog, SimulationState,
    Company, Branch, Division, CostCenter, Team, Project, Sprint, Issue, EmployeeSkill,
    Expense, Notification, CustomWidget
)
from .rules import enforce_checkout_rules
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Sum, Q, Count, Avg
import json


def login_view(request):
    if request.user.is_authenticated:
        return redirect('employee_dashboard')
        
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            AuditLog.objects.create(
                user=user,
                action="LOGIN",
                details="User logged in successfully via web interface",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            # Create employee profile if missing (helps with new users)
            profile, created = EmployeeProfile.objects.get_or_create(
                user=user,
                defaults={'employee_id': f"EMP-{user.id:04d}", 'designation': 'Software Engineer'}
            )
            SimulationState.objects.get_or_create(employee=profile)
            
            if user.is_staff or profile.manager:
                return redirect('admin_dashboard')
            return redirect('employee_dashboard')
        else:
            return render(request, 'tracker/login.html', {'error': 'Invalid username or password'})
            
    return render(request, 'tracker/login.html')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('employee_dashboard')
        
    departments = Department.objects.all()
    office_locations = OfficeLocation.objects.all()
    
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        fn = request.POST.get('first_name')
        ln = request.POST.get('last_name')
        email = request.POST.get('email')
        designation = request.POST.get('designation')
        laptop_mac = request.POST.get('laptop_mac', '').strip()
        dept_id = request.POST.get('department')
        loc_id = request.POST.get('office_location')
        
        # Check if username exists
        if User.objects.filter(username=u).exists():
            return render(request, 'tracker/register.html', {
                'error': 'Username already exists',
                'departments': departments,
                'office_locations': office_locations
            })
            
        try:
            # Create user
            user = User.objects.create_user(username=u, password=p, first_name=fn, last_name=ln, email=email)
            
            # Find department and location
            dept = Department.objects.filter(id=dept_id).first()
            loc = OfficeLocation.objects.filter(id=loc_id).first()
            
            # Create employee profile
            profile = EmployeeProfile.objects.create(
                user=user,
                employee_id=f"EMP-{user.id:04d}",
                designation=designation,
                department=dept,
                office_location=loc,
                assigned_laptop_mac=laptop_mac if laptop_mac else None,
                current_status='OFFLINE'
            )
            
            # Create simulation state
            SimulationState.objects.create(employee=profile)
            
            # Log in the user
            login(request, user)
            
            AuditLog.objects.create(
                user=user,
                action="REGISTER",
                details="New user registered successfully",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return redirect('employee_dashboard')
            
        except Exception as e:
            return render(request, 'tracker/register.html', {
                'error': f'Registration failed: {str(e)}',
                'departments': departments,
                'office_locations': office_locations
            })
            
    return render(request, 'tracker/register.html', {
        'departments': departments,
        'office_locations': office_locations
    })

def logout_view(request):
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action="LOGOUT",
            details="User logged out manually",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        logout(request)
    return redirect('login')

@login_required
def admin_dashboard(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    if not request.user.is_staff and not profile.manager:
        messages.error(request, "Access Denied: Admin or Manager credentials required.")
        return redirect('employee_dashboard')
        
    profiles = EmployeeProfile.objects.all().select_related('user', 'department')
    routers = RouterConfig.objects.all().select_related('office')
    leaves = LeaveRequest.objects.filter(status='PENDING').select_related('employee__user')
    
    total = profiles.count()
    working = profiles.filter(current_status='WORKING').count()
    idle = profiles.filter(current_status='IDLE').count()
    meeting = profiles.filter(current_status='MEETING').count()
    outside = profiles.filter(current_status='OUTSIDE').count()
    offline = profiles.filter(current_status='OFFLINE').count()
    checked_out = profiles.filter(current_status='CHECKED_OUT').count()
    
    # Calculate present count (checked in today)
    today = timezone.localdate()
    present_count = Attendance.objects.filter(date=today).count()
    leave_count = LeaveRequest.objects.filter(status='APPROVED', start_date__lte=today, end_date__gte=today).count()
    absent_count = max(0, total - present_count - leave_count)

    stats = {
        'total': total,
        'working': working,
        'idle': idle,
        'meeting': meeting,
        'outside': outside,
        'offline': offline,
        'checked_out': checked_out,
        'present_count': present_count,
        'leave_count': leave_count,
        'absent_count': absent_count
    }
    
    context = {
        'employees': profiles,
        'routers': routers,
        'leaves': leaves,
        'stats': stats
    }
    return render(request, 'tracker/admin_dashboard.html', context)

@login_required
def employee_dashboard(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    today = timezone.localdate()
    
    # Active checked-in log
    attendance = Attendance.objects.filter(employee=profile, date=today, check_out__isnull=True).first()
    past_attendance = Attendance.objects.filter(employee=profile).order_by('-date')[:10]
    
    # Build dynamic visual timeline for today
    timeline = []
    
    att = Attendance.objects.filter(employee=profile, date=today).first()
    if att:
        timeline.append({
            'time': timezone.localtime(att.check_in),
            'title': 'Checked In',
            'detail': f"Method: {att.get_check_in_method_display()}",
            'status': 'working'
        })
        if att.check_out:
            timeline.append({
                'time': timezone.localtime(att.check_out),
                'title': 'Checked Out',
                'detail': f"Method: {att.get_check_out_method_display() or 'Auto'}",
                'status': 'offline'
            })
            
    laptop_logs = LaptopActivityLog.objects.filter(employee=profile, timestamp__date=today).order_by('timestamp')
    for log in laptop_logs:
        timeline.append({
            'time': timezone.localtime(log.timestamp),
            'title': f"Laptop {log.get_state_display()}",
            'detail': f"App: {log.active_application or 'Background'} | CPU: {log.cpu_usage}%",
            'status': 'idle' if log.state in ['LOCK', 'IDLE', 'SLEEP'] else 'working'
        })
        
    outside_logs = OutsideOfficeLog.objects.filter(employee=profile, out_time__date=today).order_by('out_time')
    for log in outside_logs:
        timeline.append({
            'time': timezone.localtime(log.out_time),
            'title': 'Disappeared from WiFi Range',
            'detail': f"Reason: {log.reason}",
            'status': 'outside'
        })
        if log.return_time:
            timeline.append({
                'time': timezone.localtime(log.return_time),
                'title': 'Connected back to Office Router',
                'detail': 'Returned to desk WiFi range',
                'status': 'working'
            })
            
    internet_logs = InternetStatusLog.objects.filter(employee=profile, offline_start__date=today).order_by('offline_start')
    for log in internet_logs:
        timeline.append({
            'time': timezone.localtime(log.offline_start),
            'title': 'Internet Offline Event',
            'detail': 'Local network dropped connection',
            'status': 'offline'
        })
        if log.online_return:
            timeline.append({
                'time': timezone.localtime(log.online_return),
                'title': 'Internet Restored',
                'detail': 'Online network detected',
                'status': 'working'
            })
            
    # Sort timeline elements chronologically
    timeline.sort(key=lambda x: x['time'])
    
    context = {
        'profile': profile,
        'attendance': attendance,
        'past_attendance': past_attendance,
        'timeline': timeline
    }
    return render(request, 'tracker/employee_dashboard.html', context)

@login_required
def employee_checkin(request):
    if request.method == 'POST':
        profile = get_object_or_404(EmployeeProfile, user=request.user)
        today = timezone.localdate()
        
        # Check if already checked in today
        attendance = Attendance.objects.filter(employee=profile, date=today).first()
        if attendance:
            # Resume existing check-in session for today
            attendance.check_out = None
            attendance.save()
        else:
            # Create a brand new check-in record for today
            Attendance.objects.create(
                employee=profile,
                date=today,
                check_in=timezone.now(),
                check_in_method='MANUAL',
                status='PRESENT'
            )
        
        profile.current_status = 'WORKING'
        profile.last_status_change = timezone.now()
        profile.save()
        
        AuditLog.objects.create(
            user=request.user,
            action="CHECK_IN",
            details="Employee checked in manually via web portal",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, "Check-in successful. Have a productive day!")
            
    return redirect('employee_dashboard')

@login_required
def employee_checkout(request):
    if request.method == 'POST':
        profile = get_object_or_404(EmployeeProfile, user=request.user)
        
        # Strict 9-hour daily work requirement check
        if profile.working_hours_today < 9.0:
            rem = 9.0 - profile.working_hours_today
            messages.error(request, f"Checkout Blocked: You must complete at least 9.0 working hours today. (Remaining: {rem:.1f} hours)")
            return redirect('employee_dashboard')
            
        today = timezone.localdate()
        
        attendance = Attendance.objects.filter(employee=profile, date=today, check_out__isnull=True).first()
        if attendance:
            now = timezone.now()
            attendance.check_out = now
            attendance.check_out_method = 'MANUAL'
            
            # Compute duration in hours
            diff = now - attendance.check_in
            attendance.total_hours = max(0.1, round(diff.total_seconds() / 3600.0, 2))
            attendance.save()
            
            profile.current_status = 'CHECKED_OUT'
            profile.last_status_change = timezone.now()
            profile.save()
            
            # Reset simulator states upon check-out
            sim_state, _ = SimulationState.objects.get_or_create(employee=profile)
            sim_state.wifi_disconnect_duration = 0
            sim_state.internet_lost_duration = 0
            sim_state.browser_closed_duration = 0
            sim_state.laptop_sleep_duration = 0
            sim_state.idle_duration = 0
            sim_state.save()
            
            AuditLog.objects.create(
                user=request.user,
                action="CHECK_OUT",
                details="Employee checked out manually via web portal",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Check-out successful. See you tomorrow!")
            
    return redirect('employee_dashboard')

@login_required
def employee_status_change(request):
    if request.method == 'POST':
        profile = get_object_or_404(EmployeeProfile, user=request.user)
        new_status = request.POST.get('status')
        if new_status in ['WORKING', 'IDLE', 'MEETING']:
            old = profile.current_status
            profile.current_status = new_status
            profile.last_status_change = timezone.now()
            profile.save()
            
            AuditLog.objects.create(
                user=request.user,
                action="STATUS_CHANGE",
                details=f"Employee changed status manually from {old} to {new_status}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
    return redirect('employee_dashboard')

@login_required
def submit_leave(request):
    if request.method == 'POST':
        profile = get_object_or_404(EmployeeProfile, user=request.user)
        LeaveRequest.objects.create(
            employee=profile,
            leave_type=request.POST.get('leave_type'),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date'),
            reason=request.POST.get('reason'),
            status='PENDING'
        )
        messages.success(request, "Leave request submitted successfully.")
    return redirect('employee_dashboard')

@login_required
def approve_leave(request, leave_id):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    if not request.user.is_staff and not profile.manager:
        messages.error(request, "Unauthorized operation.")
        return redirect('employee_dashboard')
        
    if request.method == 'POST':
        leave = get_object_or_404(LeaveRequest, id=leave_id)
        action = request.POST.get('action')
        
        if action == 'approve':
            leave.status = 'APPROVED'
            leave.approved_by = profile
            leave.save()
            messages.success(request, f"Leave request for {leave.employee.user.username} approved.")
        elif action == 'reject':
            leave.status = 'REJECTED'
            leave.approved_by = profile
            leave.save()
            messages.success(request, f"Leave request for {leave.employee.user.username} rejected.")
            
    return redirect('admin_dashboard')

@login_required
def simulator_view(request):
    # Choose profile to simulate
    profile_id = request.GET.get('employee_id')
    if profile_id:
        active_profile = get_object_or_404(EmployeeProfile, id=profile_id)
    else:
        active_profile = get_object_or_404(EmployeeProfile, user=request.user)
        
    sim_state, _ = SimulationState.objects.get_or_create(employee=active_profile)
    employees = EmployeeProfile.objects.all().select_related('user')
    
    # Grab timeline of the active simulated profile
    today = timezone.localdate()
    timeline = []
    
    att = Attendance.objects.filter(employee=active_profile, date=today).first()
    if att:
        timeline.append({
            'time': timezone.localtime(att.check_in),
            'title': 'Checked In',
            'detail': f"Method: {att.get_check_in_method_display()}",
            'status': 'working'
        })
        if att.check_out:
            timeline.append({
                'time': timezone.localtime(att.check_out),
                'title': 'Checked Out',
                'detail': f"Method: {att.get_check_out_method_display() or 'Auto'}",
                'status': 'offline'
            })
            
    laptop_logs = LaptopActivityLog.objects.filter(employee=active_profile, timestamp__date=today).order_by('timestamp')
    for log in laptop_logs:
        timeline.append({
            'time': timezone.localtime(log.timestamp),
            'title': f"Laptop {log.get_state_display()}",
            'detail': f"CPU: {log.cpu_usage}% | App: {log.active_application or 'System'}",
            'status': 'idle' if log.state in ['LOCK', 'IDLE', 'SLEEP'] else 'working'
        })
        
    outside_logs = OutsideOfficeLog.objects.filter(employee=active_profile, out_time__date=today)
    for log in outside_logs:
        timeline.append({
            'time': timezone.localtime(log.out_time),
            'title': 'WiFi Outage Detected',
            'detail': f"Reason: {log.reason}",
            'status': 'outside'
        })
        if log.return_time:
            timeline.append({
                'time': timezone.localtime(log.return_time),
                'title': 'WiFi Signal Restored',
                'detail': 'Returned to desk range',
                'status': 'working'
            })

    timeline.sort(key=lambda x: x['time'])

    context = {
        'employees': employees,
        'active_profile': active_profile,
        'sim_state': sim_state,
        'timeline': timeline
    }
    return render(request, 'tracker/simulator.html', context)

@login_required
def reports_view(request):
    report_type = request.GET.get('type', 'attendance')
    records = []
    
    if report_type == 'attendance':
        records = Attendance.objects.all().select_related('employee__user').order_by('-date', '-check_in')
    elif report_type == 'outside':
        records = OutsideOfficeLog.objects.all().select_related('employee__user').order_by('-out_time')
    elif report_type == 'internet':
        records = InternetStatusLog.objects.all().select_related('employee__user').order_by('-offline_start')
    elif report_type == 'laptop':
        records = LaptopActivityLog.objects.all().select_related('employee__user').order_by('-timestamp')
    elif report_type == 'productivity':
        records = EmployeeProfile.objects.all().select_related('user').order_by('-working_hours_today')
    elif report_type == 'audit':
        records = AuditLog.objects.all().select_related('user').order_by('-timestamp')
        
    context = {
        'active_report': report_type,
        'records': records
    }
    return render(request, 'tracker/reports.html', context)

@login_required
def employee_profile_detail(request, profile_id):
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    today = timezone.localdate()
    
    # Timeline logs compilation
    timeline = []
    
    att = Attendance.objects.filter(employee=profile, date=today).first()
    if att:
        timeline.append({
            'time': timezone.localtime(att.check_in),
            'title': 'Checked In',
            'detail': f"Method: {att.get_check_in_method_display()}",
            'status': 'working'
        })
        if att.check_out:
            timeline.append({
                'time': timezone.localtime(att.check_out),
                'title': 'Checked Out',
                'detail': f"Method: {att.get_check_out_method_display() or 'Auto'}",
                'status': 'offline'
            })
            
    laptop_logs = LaptopActivityLog.objects.filter(employee=profile, timestamp__date=today).order_by('timestamp')
    for log in laptop_logs:
        timeline.append({
            'time': timezone.localtime(log.timestamp),
            'title': f"Laptop {log.get_state_display()}",
            'detail': f"App: {log.active_application or '-'} | CPU: {log.cpu_usage}%",
            'status': 'idle' if log.state in ['LOCK', 'IDLE', 'SLEEP'] else 'working'
        })
        
    outside_logs = OutsideOfficeLog.objects.filter(employee=profile, out_time__date=today)
    for log in outside_logs:
        timeline.append({
            'time': timezone.localtime(log.out_time),
            'title': 'WiFi Outage Detected',
            'detail': f"Reason: {log.reason}",
            'status': 'outside'
        })
        if log.return_time:
            timeline.append({
                'time': timezone.localtime(log.return_time),
                'title': 'WiFi Signal Restored',
                'detail': 'Returned to desk',
                'status': 'working'
            })

    timeline.sort(key=lambda x: x['time'])
    
    context = {
        'profile': profile,
        'timeline': timeline
    }
    return render(request, 'tracker/employee_profile_detail.html', context)


# --- OFFICE TRACKING & PROJECT MANAGEMENT VIEWS ---

@login_required
def dashboard_hub(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    active_tab = request.GET.get('tab', 'personal')
    today = timezone.localdate()
    
    # Notifications
    notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')
    
    # Handle mark notification as read
    if request.method == 'POST' and request.POST.get('action') == 'read_notification':
        notif_id = request.POST.get('notification_id')
        Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
        return redirect(f"/dashboard/hub/?tab={active_tab}")

    # Initialize widgets customization
    widgets_config = CustomWidget.objects.filter(user=request.user, is_enabled=True).values_list('widget_type', flat=True)
    if not widgets_config.exists() and not CustomWidget.objects.filter(user=request.user).exists():
        # Default widgets
        default_widgets = ["WORKLOAD", "DEADLINES", "PERFORMANCE", "CALENDAR", "HEALTH", "ATTENDANCE"]
        for idx, w_type in enumerate(default_widgets):
            CustomWidget.objects.create(user=request.user, widget_type=w_type, is_enabled=True, order=idx)
        widgets_config = default_widgets

    # Common Context
    context = {
        'active_tab': active_tab,
        'profile': profile,
        'notifications': notifications,
        'widgets_config': widgets_config,
    }

    # 1. PERSONAL DASHBOARD
    if active_tab == 'personal':
        # Today's attendance
        attendance = Attendance.objects.filter(employee=profile, date=today).first()
        # Personal Tasks / Issues
        personal_issues = Issue.objects.filter(assignee=profile).exclude(status='DONE').order_by('due_date')
        completed_issues_count = Issue.objects.filter(assignee=profile, status='DONE').count()
        pending_issues_count = personal_issues.count()
        # Upcoming Deadlines
        upcoming_deadlines = personal_issues.filter(due_date__isnull=False, due_date__gte=today, due_date__lte=today + timezone.timedelta(days=7))
        # Leave status
        applied_leaves = LeaveRequest.objects.filter(employee=profile).order_by('-start_date')
        
        context.update({
            'attendance': attendance,
            'personal_issues': personal_issues,
            'completed_issues_count': completed_issues_count,
            'pending_issues_count': pending_issues_count,
            'upcoming_deadlines': upcoming_deadlines,
            'applied_leaves': applied_leaves,
        })

    # 2. EXECUTIVE DASHBOARD
    elif active_tab == 'executive':
        if not request.user.is_superuser and profile.role not in ['ADMIN', 'EXECUTIVE']:
            messages.error(request, "Access Denied: Executive credentials required.")
            return redirect("/dashboard/hub/?tab=personal")
            
        total_projects = Project.objects.count()
        active_projects = Project.objects.filter(status='ACTIVE')
        total_employees = EmployeeProfile.objects.count()
        total_departments = Department.objects.count()
        total_branches = Branch.objects.count()
        total_cost_centers = CostCenter.objects.count()
        
        # Budget vs Cost
        total_budget = Project.objects.aggregate(sum_budget=Sum('budget'))['sum_budget'] or 0.0
        total_cost = Project.objects.aggregate(sum_cost=Sum('cost'))['sum_cost'] or 0.0
        
        # Expenses Summary
        expenses_approved = Expense.objects.filter(status='APPROVED').aggregate(sum_amt=Sum('amount'))['sum_amt'] or 0.0
        expenses_pending = Expense.objects.filter(status='PENDING').aggregate(sum_amt=Sum('amount'))['sum_amt'] or 0.0
        
        # Recent activity (AuditLog)
        recent_activities = AuditLog.objects.all().order_by('-timestamp')[:15]
        
        # Attendance overview
        present_count = Attendance.objects.filter(date=today).count()
        checked_out_count = EmployeeProfile.objects.filter(current_status='CHECKED_OUT').count()
        offline_count = EmployeeProfile.objects.filter(current_status='OFFLINE').count()
        working_count = EmployeeProfile.objects.filter(current_status='WORKING').count()
        idle_count = EmployeeProfile.objects.filter(current_status='IDLE').count()
        meeting_count = EmployeeProfile.objects.filter(current_status='MEETING').count()
        outside_count = EmployeeProfile.objects.filter(current_status='OUTSIDE').count()

        context.update({
            'total_projects': total_projects,
            'active_projects': active_projects,
            'total_employees': total_employees,
            'total_departments': total_departments,
            'total_branches': total_branches,
            'total_cost_centers': total_cost_centers,
            'total_budget': total_budget,
            'total_cost': total_cost,
            'expenses_approved': expenses_approved,
            'expenses_pending': expenses_pending,
            'recent_activities': recent_activities,
            'present_count': present_count,
            'working_count': working_count,
            'idle_count': idle_count,
            'meeting_count': meeting_count,
            'outside_count': outside_count,
            'offline_count': offline_count,
            'checked_out_count': checked_out_count,
        })

    # 3. TEAM DASHBOARD
    elif active_tab == 'team':
        # Find employee's team(s)
        teams = Team.objects.filter(Q(members=profile) | Q(lead=profile)).distinct()
        selected_team_id = request.GET.get('team_id')
        selected_team = None
        if selected_team_id:
            selected_team = get_object_or_404(Team, id=selected_team_id)
        elif teams.exists():
            selected_team = teams.first()
            
        team_members = []
        workload_data = []
        if selected_team:
            team_members = selected_team.members.all().select_related('user')
            # Fetch workload
            for member in team_members:
                task_count = Issue.objects.filter(assignee=member).exclude(status='DONE').count()
                story_points = Issue.objects.filter(assignee=member).exclude(status='DONE').aggregate(sp=Sum('story_points'))['sp'] or 0
                workload_data.append({
                    'name': member.user.get_full_name() or member.user.username,
                    'task_count': task_count,
                    'story_points': story_points,
                    'status': member.get_current_status_display()
                })
                
        context.update({
            'teams': teams,
            'selected_team': selected_team,
            'team_members': team_members,
            'workload_data': workload_data,
        })

    # 4. PROJECT DASHBOARD
    elif active_tab == 'project':
        projects = Project.objects.filter(status='ACTIVE')
        selected_project_id = request.GET.get('project_id')
        selected_project = None
        if selected_project_id:
            selected_project = get_object_or_404(Project, id=selected_project_id)
        elif projects.exists():
            selected_project = projects.first()
            
        sprint_progress = 0
        total_points = 0
        done_points = 0
        bug_count = 0
        critical_bug_count = 0
        project_issues = []
        active_sprint = None
        
        if selected_project:
            active_sprint = Sprint.objects.filter(project=selected_project, status='ACTIVE').first()
            project_issues = Issue.objects.filter(project=selected_project)
            bug_count = project_issues.filter(issue_type='BUG').count()
            critical_bug_count = project_issues.filter(issue_type='BUG', priority='CRITICAL').count()
            
            # Sprints points
            if active_sprint:
                sprint_issues = Issue.objects.filter(sprint=active_sprint)
                total_points = sprint_issues.aggregate(sp=Sum('story_points'))['sp'] or 0
                done_points = sprint_issues.filter(status='DONE').aggregate(sp=Sum('story_points'))['sp'] or 0
                if total_points > 0:
                    sprint_progress = int((done_points / total_points) * 100)
                    
        context.update({
            'projects': projects,
            'selected_project': selected_project,
            'active_sprint': active_sprint,
            'sprint_progress': sprint_progress,
            'total_points': total_points,
            'done_points': done_points,
            'bug_count': bug_count,
            'critical_bug_count': critical_bug_count,
        })

    # 5. DEPARTMENT DASHBOARD
    elif active_tab == 'department':
        departments = Department.objects.all()
        selected_dept_id = request.GET.get('department_id')
        selected_dept = None
        if selected_dept_id:
            selected_dept = get_object_or_404(Department, id=selected_dept_id)
        elif profile.department:
            selected_dept = profile.department
        elif departments.exists():
            selected_dept = departments.first()
            
        divisions = []
        dept_employees = []
        dept_leaves = []
        
        if selected_dept:
            divisions = Division.objects.filter(department=selected_dept)
            dept_employees = EmployeeProfile.objects.filter(department=selected_dept).select_related('user')
            dept_leaves = LeaveRequest.objects.filter(employee__department=selected_dept, status='PENDING').select_related('employee__user')
            
        context.update({
            'departments': departments,
            'selected_dept': selected_dept,
            'divisions': divisions,
            'dept_employees': dept_employees,
            'dept_leaves': dept_leaves,
        })

    return render(request, 'tracker/dashboard_hub.html', context)


@login_required
def projects_list(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        key = request.POST.get('key').upper()
        description = request.POST.get('description')
        category = request.POST.get('category')
        priority = request.POST.get('priority')
        template_name = request.POST.get('template_name')
        budget = float(request.POST.get('budget', 0))
        cost_center_id = request.POST.get('cost_center')
        
        cost_center = CostCenter.objects.filter(id=cost_center_id).first()
        
        if Project.objects.filter(key=key).exists() or Project.objects.filter(name=name).exists():
            messages.error(request, f"Error: A project with name '{name}' or key '{key}' already exists.")
        else:
            project = Project.objects.create(
                name=name,
                key=key,
                description=description,
                category=category,
                priority=priority,
                template_name=template_name,
                budget=budget,
                created_by=request.user,
                cost_center=cost_center,
                start_date=timezone.localdate(),
                end_date=timezone.localdate() + timezone.timedelta(days=90)
            )
            
            # Apply Templates
            if template_name == 'SOFTWARE':
                # Create standard Sprints & issues
                s1 = Sprint.objects.create(
                    project=project,
                    name="Sprint 1",
                    start_date=timezone.localdate(),
                    end_date=timezone.localdate() + timezone.timedelta(days=14),
                    status='ACTIVE'
                )
                Sprint.objects.create(
                    project=project,
                    name="Sprint 2",
                    start_date=timezone.localdate() + timezone.timedelta(days=14),
                    end_date=timezone.localdate() + timezone.timedelta(days=28),
                    status='PLANNED'
                )
                # Sample issues
                Issue.objects.create(
                    project=project, sprint=s1, title="Design API endpoints",
                    description="Implement REST architecture for tasks retrieval.",
                    issue_type="STORY", status="TODO", priority="HIGH",
                    assignee=profile, reporter=profile, story_points=5
                )
                Issue.objects.create(
                    project=project, sprint=s1, title="Fix security tokens validation",
                    description="Resolve session leakage on desktop client pings.",
                    issue_type="BUG", status="IN_PROGRESS", priority="CRITICAL",
                    assignee=profile, reporter=profile, story_points=3
                )
            elif template_name == 'KANBAN':
                # Kanban has no sprints, just issues in backlog/todo
                Issue.objects.create(
                    project=project, title="Establish brand design system",
                    description="Define color codes, font-weights, and logo vectors.",
                    issue_type="TASK", status="TODO", priority="MEDIUM",
                    assignee=profile, reporter=profile, story_points=2
                )
            else: # GENERAL PM
                s1 = Sprint.objects.create(
                    project=project,
                    name="Phase 1",
                    start_date=timezone.localdate(),
                    end_date=timezone.localdate() + timezone.timedelta(days=30),
                    status='ACTIVE'
                )
                Issue.objects.create(
                    project=project, sprint=s1, title="Compile stakeholder feedback",
                    description="Gather feedback reports from division leaders.",
                    issue_type="TASK", status="TODO", priority="LOW",
                    assignee=profile, reporter=profile, story_points=1
                )
                
            messages.success(request, f"Project '{name}' successfully created using {template_name} template!")
            return redirect('projects_list')

    projects = Project.objects.all().order_by('-start_date')
    cost_centers = CostCenter.objects.all()
    
    # Calculate dynamically derived costs for projects
    for proj in projects:
        # Sum of approved expenses
        approved_expenses_sum = Expense.objects.filter(project=proj, status='APPROVED').aggregate(sum_amt=Sum('amount'))['sum_amt'] or 0.0
        # Dynamic employee labor cost: hours worked * rate (mock: FULL_TIME=40/hr, CONTRACTOR=50/hr, PART_TIME=25/hr)
        labor_cost = 0.0
        assignees = EmployeeProfile.objects.filter(assigned_issues__project=proj).distinct()
        for dev in assignees:
            total_hours = Attendance.objects.filter(employee=dev, date__gte=proj.start_date, date__lte=proj.end_date).aggregate(hrs=Sum('total_hours'))['hrs'] or 0.0
            rate = 35.0
            if dev.employment_type == 'CONTRACTOR':
                rate = 50.0
            elif dev.employment_type == 'PART_TIME':
                rate = 25.0
            labor_cost += (total_hours * rate)
            
        proj.cost = round(approved_expenses_sum + labor_cost, 2)
        proj.save()

    context = {
        'projects': projects,
        'cost_centers': cost_centers,
        'profile': profile,
    }
    return render(request, 'tracker/projects.html', context)


@login_required
def project_board(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    # Active Sprints, Planned Sprints, Completed Sprints
    active_sprint = Sprint.objects.filter(project=project, status='ACTIVE').first()
    planned_sprints = Sprint.objects.filter(project=project, status='PLANNED')
    completed_sprints = Sprint.objects.filter(project=project, status='COMPLETED')
    
    # Issues
    backlog_issues = Issue.objects.filter(project=project, sprint__isnull=True)
    board_issues = Issue.objects.filter(project=project)
    if active_sprint:
        board_issues = board_issues.filter(sprint=active_sprint)
    else:
        board_issues = board_issues.filter(sprint__isnull=True)
        
    todo_issues = board_issues.filter(status='TODO')
    inprogress_issues = board_issues.filter(status='IN_PROGRESS')
    inreview_issues = board_issues.filter(status='IN_REVIEW')
    done_issues = board_issues.filter(status='DONE')
    
    # Timeline Gantt issues
    timeline_issues = Issue.objects.filter(project=project, due_date__isnull=False).order_by('created_at')

    # All employees for dropdown assignee
    employees = EmployeeProfile.objects.all().select_related('user')

    context = {
        'project': project,
        'profile': profile,
        'active_sprint': active_sprint,
        'planned_sprints': planned_sprints,
        'completed_sprints': completed_sprints,
        'backlog_issues': backlog_issues,
        'todo_issues': todo_issues,
        'inprogress_issues': inprogress_issues,
        'inreview_issues': inreview_issues,
        'done_issues': done_issues,
        'timeline_issues': timeline_issues,
        'employees': employees,
    }
    return render(request, 'tracker/project_detail.html', context)


@login_required
def project_clone(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if request.method == 'POST':
        new_name = request.POST.get('name')
        new_key = request.POST.get('key').upper()
        
        if Project.objects.filter(key=new_key).exists() or Project.objects.filter(name=new_name).exists():
            messages.error(request, f"Error: A project with name '{new_name}' or key '{new_key}' already exists.")
        else:
            new_project = Project.objects.create(
                name=new_name,
                key=new_key,
                description=f"Cloned from {project.name}. {project.description}",
                category=project.category,
                priority=project.priority,
                status='ACTIVE',
                template_name=project.template_name,
                budget=project.budget,
                cost=0.0,
                start_date=timezone.localdate(),
                end_date=timezone.localdate() + timezone.timedelta(days=90),
                created_by=request.user,
                cost_center=project.cost_center
            )
            
            # Clone sprints and issue templates
            sprints_map = {}
            for sprint in project.sprints.all():
                new_sprint = Sprint.objects.create(
                    project=new_project,
                    name=sprint.name,
                    start_date=timezone.localdate(),
                    end_date=timezone.localdate() + timezone.timedelta(days=14),
                    status='PLANNED'
                )
                sprints_map[sprint.id] = new_sprint
                
            # Clone issues
            for issue in project.issues.all():
                Issue.objects.create(
                    project=new_project,
                    sprint=sprints_map.get(issue.sprint_id) if issue.sprint else None,
                    title=issue.title,
                    description=issue.description,
                    issue_type=issue.issue_type,
                    status='BACKLOG',
                    priority=issue.priority,
                    reporter=issue.reporter,
                    story_points=issue.story_points
                )
                
            messages.success(request, f"Project '{project.name}' successfully cloned into '{new_name}'!")
            
    return redirect('projects_list')


@login_required
def project_archive(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    project.status = 'ARCHIVED'
    project.save()
    messages.success(request, f"Project '{project.name}' successfully archived.")
    return redirect('projects_list')


@login_required
def project_delete(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    name = project.name
    project.delete()
    messages.success(request, f"Project '{name}' successfully deleted.")
    return redirect('projects_list')


@login_required
def create_issue(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        issue_type = request.POST.get('issue_type')
        priority = request.POST.get('priority')
        assignee_id = request.POST.get('assignee')
        story_points = int(request.POST.get('story_points', 0))
        due_date = request.POST.get('due_date')
        
        assignee = None
        if assignee_id:
            assignee = EmployeeProfile.objects.filter(id=assignee_id).first()
            
        sprint = Sprint.objects.filter(project=project, status='ACTIVE').first()
        
        Issue.objects.create(
            project=project,
            sprint=sprint,
            title=title,
            description=description,
            issue_type=issue_type,
            status='TODO' if sprint else 'BACKLOG',
            priority=priority,
            assignee=assignee,
            reporter=profile,
            story_points=story_points,
            due_date=due_date if due_date else None
        )
        
        # Add Notification to Assignee
        if assignee and assignee.user != request.user:
            Notification.objects.create(
                user=assignee.user,
                message=f"You have been assigned to task: '{title}' in project {project.name}"
            )
            
        messages.success(request, f"Task '{title}' created successfully!")
        
    return redirect('project_board', project_id=project.id)


@csrf_exempt
@login_required
def update_issue_status(request, issue_id):
    issue = get_object_or_404(Issue, id=issue_id)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_status = data.get('status')
            if new_status in ['BACKLOG', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE']:
                old_status = issue.status
                issue.status = new_status
                issue.save()
                
                # Audit log
                AuditLog.objects.create(
                    user=request.user,
                    action="ISSUE_TRANSITION",
                    details=f"Issue '{issue.title}' moved from {old_status} to {new_status}"
                )
                
                return JsonResponse({'success': True, 'message': 'Status updated'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
            
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@login_required
def organization_hub(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    companies = Company.objects.all()
    branches = Branch.objects.all().select_related('company')
    divisions = Division.objects.all().select_related('department')
    cost_centers = CostCenter.objects.all()
    office_locations = OfficeLocation.objects.all()
    
    # Hierarchy visual construction
    hierarchy = EmployeeProfile.objects.filter(manager__isnull=True).select_related('user')
    if not hierarchy.exists() and EmployeeProfile.objects.exists():
        hierarchy = [EmployeeProfile.objects.first()]
        
    context = {
        'profile': profile,
        'companies': companies,
        'branches': branches,
        'divisions': divisions,
        'cost_centers': cost_centers,
        'office_locations': office_locations,
        'hierarchy': hierarchy,
    }
    return render(request, 'tracker/organization.html', context)


@login_required
def user_management_hub(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    # Check roles permissions
    if not request.user.is_superuser and profile.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "Access Denied: Managers or Admins only.")
        return redirect('employee_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. Create Team
        if action == 'create_team':
            t_name = request.POST.get('name')
            dept_id = request.POST.get('department')
            lead_id = request.POST.get('lead')
            t_desc = request.POST.get('description')
            
            lead = EmployeeProfile.objects.filter(id=lead_id).first()
            dept = Department.objects.filter(id=dept_id).first()
            
            team = Team.objects.create(name=t_name, department=dept, lead=lead, description=t_desc)
            member_ids = request.POST.getlist('members')
            if member_ids:
                m_profiles = EmployeeProfile.objects.filter(id__in=member_ids)
                team.members.set(m_profiles)
            messages.success(request, f"Team '{t_name}' successfully created!")
            
        # 2. Modify Role
        elif action == 'modify_role':
            target_profile_id = request.POST.get('profile_id')
            new_role = request.POST.get('role')
            target_prof = get_object_or_404(EmployeeProfile, id=target_profile_id)
            old_role = target_prof.role
            target_prof.role = new_role
            
            if new_role in ['ADMIN', 'EXECUTIVE']:
                target_prof.user.is_staff = True
            else:
                target_prof.user.is_staff = False
            target_prof.user.save()
            target_prof.save()
            
            AuditLog.objects.create(
                user=request.user,
                action="ROLE_MODIFIED",
                details=f"Modified role of {target_prof} from {old_role} to {new_role}"
            )
            messages.success(request, f"User role for {target_prof} updated to {new_role}.")
            
        return redirect('user_management_hub')

    profiles = EmployeeProfile.objects.all().select_related('user', 'department')
    teams = Team.objects.all().select_related('department', 'lead')
    departments = Department.objects.all()
    login_history = AuditLog.objects.filter(Q(action="LOGIN") | Q(action="LOGOUT")).order_by('-timestamp')[:20]
    activity_logs = AuditLog.objects.all().order_by('-timestamp')[:30]

    context = {
        'profile': profile,
        'profiles': profiles,
        'teams': teams,
        'departments': departments,
        'login_history': login_history,
        'activity_logs': activity_logs,
    }
    return render(request, 'tracker/users.html', context)


@csrf_exempt
@login_required
def add_skill(request, profile_id):
    prof = get_object_or_404(EmployeeProfile, id=profile_id)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            skill_name = data.get('skill_name')
            proficiency = data.get('proficiency', 'INTERMEDIATE')
            if skill_name:
                skill, created = EmployeeSkill.objects.get_or_create(
                    employee=prof,
                    skill_name=skill_name,
                    defaults={'proficiency': proficiency}
                )
                if not created:
                    skill.proficiency = proficiency
                    skill.save()
                return JsonResponse({'success': True, 'message': 'Skill updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid Request'}, status=400)


@csrf_exempt
@login_required
def delete_skill(request, profile_id, skill_id):
    prof = get_object_or_404(EmployeeProfile, id=profile_id)
    if request.method == 'POST':
        try:
            skill = get_object_or_404(EmployeeSkill, id=skill_id, employee=prof)
            skill.delete()
            return JsonResponse({'success': True, 'message': 'Skill removed'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid Request'}, status=400)


@login_required
def expense_tracker(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Claims submission
        if action == 'claim_expense':
            project_id = request.POST.get('project')
            amount = float(request.POST.get('amount'))
            category = request.POST.get('category')
            description = request.POST.get('description')
            
            project = Project.objects.filter(id=project_id).first()
            
            Expense.objects.create(
                employee=profile,
                project=project,
                amount=amount,
                category=category,
                description=description,
                status='PENDING'
            )
            messages.success(request, f"Expense claim of ${amount:.2f} filed successfully.")
            
        return redirect('expense_tracker')

    my_expenses = Expense.objects.filter(employee=profile).order_by('-date')
    pending_approvals = Expense.objects.filter(status='PENDING').select_related('employee__user', 'project')
    approved_expenses = Expense.objects.filter(status='APPROVED').select_related('employee__user', 'project')
    
    projects = Project.objects.filter(status='ACTIVE')
    
    context = {
        'profile': profile,
        'my_expenses': my_expenses,
        'pending_approvals': pending_approvals,
        'approved_expenses': approved_expenses,
        'projects': projects,
    }
    return render(request, 'tracker/expenses.html', context)


@login_required
def approve_expense(request, expense_id):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    if not request.user.is_staff and profile.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "Access Denied: Managers or Admins only.")
        return redirect('expense_tracker')
        
    expense = get_object_or_404(Expense, id=expense_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            expense.status = 'APPROVED'
            expense.approved_by = profile
            expense.save()
            messages.success(request, "Expense request approved successfully.")
            
            if expense.project:
                expense.project.cost += expense.amount
                expense.project.save()
        elif action == 'reject':
            expense.status = 'REJECTED'
            expense.approved_by = profile
            expense.save()
            messages.success(request, "Expense request rejected.")
            
    return redirect('expense_tracker')


@login_required
def settings_panel(request):
    profile = get_object_or_404(EmployeeProfile, user=request.user)
    
    if request.method == 'POST':
        widget_types = ["WORKLOAD", "DEADLINES", "PERFORMANCE", "CALENDAR", "HEALTH", "ATTENDANCE"]
        CustomWidget.objects.filter(user=request.user).update(is_enabled=False)
        for idx, w_type in enumerate(widget_types):
            enabled_val = request.POST.get(f"widget_{w_type}") == 'on'
            w_obj, _ = CustomWidget.objects.get_or_create(user=request.user, widget_type=w_type)
            w_obj.is_enabled = enabled_val
            w_obj.order = idx
            w_obj.save()
            
        messages.success(request, "Portal settings saved successfully.")
        return redirect('settings_panel')
        
    widgets = CustomWidget.objects.filter(user=request.user).order_by('order')
    
    context = {
        'profile': profile,
        'widgets': widgets,
    }
    return render(request, 'tracker/settings.html', context)
