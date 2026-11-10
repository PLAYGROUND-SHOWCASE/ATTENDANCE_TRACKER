from django.urls import path
from django.shortcuts import redirect
from . import views, api

urlpatterns = [
    # Root Redirect
    path('', lambda r: redirect('login')),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboards
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('portal/', views.employee_dashboard, name='employee_dashboard'),
    path('dashboard/hub/', views.dashboard_hub, name='dashboard_hub'),
    
    # Project Management
    path('projects/', views.projects_list, name='projects_list'),
    path('projects/<int:project_id>/board/', views.project_board, name='project_board'),
    path('projects/<int:project_id>/clone/', views.project_clone, name='project_clone'),
    path('projects/<int:project_id>/archive/', views.project_archive, name='project_archive'),
    path('projects/<int:project_id>/delete/', views.project_delete, name='project_delete'),
    path('projects/<int:project_id>/issue/create/', views.create_issue, name='create_issue'),
    path('api/issue/<int:issue_id>/status/', views.update_issue_status, name='update_issue_status'),
    
    # Organization Management
    path('organization/', views.organization_hub, name='organization_hub'),
    
    # User Management & Teams
    path('users/', views.user_management_hub, name='user_management_hub'),
    path('users/<int:profile_id>/skills/add/', views.add_skill, name='add_skill'),
    path('users/<int:profile_id>/skills/delete/<int:skill_id>/', views.delete_skill, name='delete_skill'),
    
    # Expenses & Settings
    path('expenses/', views.expense_tracker, name='expense_tracker'),
    path('expenses/<int:expense_id>/approve/', views.approve_expense, name='approve_expense'),
    path('settings/', views.settings_panel, name='settings_panel'),

    # Employee Console Operations
    path('portal/checkin/', views.employee_checkin, name='employee_checkin'),
    path('portal/checkout/', views.employee_checkout, name='employee_checkout'),
    path('portal/status/', views.employee_status_change, name='employee_status_change'),
    path('portal/leave/', views.submit_leave, name='submit_leave'),
    
    # Manager Overrides
    path('leave/approve/<int:leave_id>/', views.approve_leave, name='approve_leave'),
    path('employee/<int:profile_id>/', views.employee_profile_detail, name='employee_profile_detail'),
    
    # Simulator
    path('simulator/', views.simulator_view, name='simulator'),
    
    # Reports
    path('reports/', views.reports_view, name='reports'),
    
    # REST API & Polling endpoints
    path('api/dashboard/stats/', api.get_dashboard_stats, name='api_dashboard_stats'),
    path('api/simulator/event/', api.simulated_event, name='api_simulated_event'),
    path('api/agent/ping/', api.agent_ping, name='api_agent_ping'),
    path('api/router/ping/', api.router_ping, name='api_router_ping'),
]
