import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import EmployeeProfile, Attendance, RouterConfig, RouterPresenceLog, LaptopActivityLog, SimulationState, AuditLog
from .rules import enforce_checkout_rules

@login_required
def get_dashboard_stats(request):
    """
    Returns aggregated live metrics and the current status breakdown of all employees for AJAX polling.
    """
    profiles = EmployeeProfile.objects.all().select_related('user', 'department')
    total = profiles.count()
    
    stats = {
        'total': total,
        'working': profiles.filter(current_status='WORKING').count(),
        'idle': profiles.filter(current_status='IDLE').count(),
        'meeting': profiles.filter(current_status='MEETING').count(),
        'outside': profiles.filter(current_status='OUTSIDE').count(),
        'offline': profiles.filter(current_status='OFFLINE').count(),
        'checked_out': profiles.filter(current_status='CHECKED_OUT').count(),
    }
    
    employee_list = []
    for p in profiles:
        # Calculate session duration
        today = timezone.localdate()
        attendance = Attendance.objects.filter(employee=p, date=today, check_out__isnull=True).first()
        duration_str = "-"
        if attendance:
            diff = timezone.now() - attendance.check_in
            hours, remainder = divmod(diff.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            duration_str = f"{int(hours)}h {int(minutes)}m"

        employee_list.append({
            'id': p.id,
            'name': p.user.get_full_name() or p.user.username,
            'employee_id': p.employee_id,
            'status': p.current_status,
            'mac': p.assigned_laptop_mac,
            'ip': p.last_seen_ip,
            'duration': duration_str,
            'today_hours': p.working_hours_today,
            'idle_hours': p.idle_hours_today
        })
        
    return JsonResponse({
        'stats': stats,
        'employees': employee_list
    })

@csrf_exempt
def simulated_event(request):
    """
    API called by the simulator panel to trigger network drops, state changes, or time-skips.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST allowed'}, status=400)
        
    try:
        data = json.loads(request.body)
        employee_id = data.get('employee_id')
        action = data.get('action')
        
        profile = EmployeeProfile.objects.get(id=employee_id)
        # Create sim state if it doesn't exist
        sim_state, _ = SimulationState.objects.get_or_create(employee=profile)
        
        message = ""
        success = True
        
        if action == 'router_connect':
            sim_state.wifi_connected = True
            sim_state.wifi_disconnect_duration = 0
            sim_state.save()
            
            # Record router presence log
            router = RouterConfig.objects.first()
            if router:
                RouterPresenceLog.objects.create(
                    employee=profile,
                    router=router,
                    local_ip="192.168.1.105",
                    signal_strength="EXCELLENT"
                )
            
            message = "WiFi Connected. Office range presence detected."
            
        elif action == 'router_disconnect':
            sim_state.wifi_connected = False
            sim_state.save()
            message = "WiFi Disconnected. Employee registered as OUTSIDE office WiFi range."
            
        elif action == 'phone_connect':
            sim_state.phone_connected = True
            sim_state.phone_disconnect_duration = 0
            sim_state.save()
            message = "Phone Connected to Office WiFi."
            
        elif action == 'phone_disconnect':
            sim_state.phone_connected = False
            sim_state.save()
            message = "Phone Disconnected from Office WiFi."
            
        elif action == 'set_distance':
            dist = float(data.get('distance', 2.0))
            sim_state.phone_laptop_distance = dist
            sim_state.save()
            message = f"Device separation distance set to {dist} meters."
            
        elif action == 'laptop_active':
            sim_state.laptop_state = 'ACTIVE'
            sim_state.idle_duration = 0
            sim_state.save()
            
            LaptopActivityLog.objects.create(
                employee=profile,
                state='ACTIVE',
                cpu_usage=18.5,
                active_application="VS Code"
            )
            message = "Laptop active. Keyboard and mouse inputs registered."
            
        elif action == 'laptop_lock':
            sim_state.laptop_state = 'LOCK'
            sim_state.save()
            LaptopActivityLog.objects.create(
                employee=profile,
                state='LOCK',
                cpu_usage=2.1
            )
            message = "Laptop locked. Status set to Idle."
            
        elif action == 'laptop_unlock':
            sim_state.laptop_state = 'ACTIVE'
            sim_state.save()
            LaptopActivityLog.objects.create(
                employee=profile,
                state='UNLOCK',
                cpu_usage=12.4
            )
            message = "Laptop screen unlocked."
            
        elif action == 'laptop_sleep':
            sim_state.laptop_state = 'SLEEP'
            sim_state.laptop_sleep_duration = 0
            sim_state.save()
            LaptopActivityLog.objects.create(
                employee=profile,
                state='SLEEP',
                cpu_usage=0.5
            )
            message = "Laptop in sleep mode. 15-minute checkout countdown started."
            
        elif action == 'laptop_shutdown':
            sim_state.laptop_state = 'OFF'
            sim_state.save()
            # Triggers immediate checkout via the rules engine
            message = "Laptop powered off. Immediate checkout triggered."
            
        elif action == 'internet_online':
            sim_state.internet_active = True
            sim_state.internet_lost_duration = 0
            sim_state.save()
            message = "Internet connectivity restored."
            
        elif action == 'internet_offline':
            sim_state.internet_active = False
            sim_state.save()
            message = "Internet connection dropped. 10-minute checkout countdown started."
            
        elif action == 'browser_open':
            sim_state.browser_open = True
            sim_state.browser_closed_duration = 0
            sim_state.save()
            message = "Portal dashboard tab opened and focused."
            
        elif action == 'browser_close':
            sim_state.browser_open = False
            sim_state.save()
            message = "Portal tab closed. 10-minute checkout countdown started."
            
        elif action == 'activity_active':
            sim_state.idle_duration = 0
            sim_state.save()
            message = "Registered device user inputs. Idle timers reset."
            
        elif action == 'activity_idle':
            sim_state.idle_duration = 10  # Jump straight to idle warning threshold
            sim_state.save()
            message = "Inactivity detected. Employee set to Idle."
            
        elif action == 'tick_time':
            minutes = int(data.get('minutes', 5))
            # Run rules engine and advance the simulators' clocks
            checkout_fired, msg = enforce_checkout_rules(profile, time_passed_minutes=minutes)
            return JsonResponse({
                'success': True,
                'message': f"Simulated {minutes} minutes passing. {msg}"
            })
            
        else:
            success = False
            message = "Invalid action specified."

        # Evaluate rules engine immediately for the action state change
        checkout_fired, rule_msg = enforce_checkout_rules(profile, time_passed_minutes=0)
        if checkout_fired:
            message = f"{message} {rule_msg}"
            
        return JsonResponse({
            'success': success,
            'message': message
        })
        
    except EmployeeProfile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=550)

@csrf_exempt
def agent_ping(request):
    """
    REST API endpoint for real desktop agents (Windows/Mac/Linux).
    Pings every 1 minute with system metrics.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST allowed'}, status=400)
    try:
        data = json.loads(request.body)
        mac_addr = data.get('mac_address')
        state = data.get('state', 'ACTIVE') # ACTIVE, SLEEP, LOCK, IDLE
        cpu = float(data.get('cpu_usage', 0.0))
        active_app = data.get('active_app', '')
        idle_seconds = int(data.get('idle_seconds', 0))
        
        profile = EmployeeProfile.objects.get(assigned_laptop_mac=mac_addr)
        profile.last_active_time = timezone.now()
        profile.last_seen_ip = request.META.get('REMOTE_ADDR')
        profile.save()
        
        # Save laptop activity log
        LaptopActivityLog.objects.create(
            employee=profile,
            state=state,
            idle_duration_seconds=idle_seconds,
            active_application=active_app,
            cpu_usage=cpu
        )
        
        # Update sim state params with actual ping data
        sim_state, _ = SimulationState.objects.get_or_create(employee=profile)
        sim_state.laptop_state = state
        if state == 'ACTIVE':
            sim_state.idle_duration = 0
        else:
            sim_state.idle_duration = int(idle_seconds / 60)
        sim_state.save()
        
        enforce_checkout_rules(profile, time_passed_minutes=1)
        
        return JsonResponse({'success': True, 'message': 'Ping received'})
    except EmployeeProfile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Unrecognized device MAC address'}, status=403)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@csrf_exempt
def router_ping(request):
    """
    REST API endpoint for router syslog or API monitoring.
    Receives list of active MAC addresses on WiFi.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST allowed'}, status=400)
    try:
        data = json.loads(request.body)
        connected_macs = [mac.upper() for mac in data.get('mac_list', [])]
        router_ip = data.get('router_ip', '192.168.1.1')
        
        router = RouterConfig.objects.get(gateway_ip=router_ip)
        router.last_ping = timezone.now()
        router.is_online = True
        router.save()
        
        # Update connection state of all employees
        profiles = EmployeeProfile.objects.filter(assigned_laptop_mac__isnull=False)
        for p in profiles:
            sim_state, _ = SimulationState.objects.get_or_create(employee=p)
            if p.assigned_laptop_mac.upper() in connected_macs:
                sim_state.wifi_connected = True
                sim_state.wifi_disconnect_duration = 0
            else:
                sim_state.wifi_connected = False
            sim_state.save()
            enforce_checkout_rules(p, time_passed_minutes=1)
            
        return JsonResponse({'success': True, 'message': 'Router logs synchronized'})
    except RouterConfig.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Unconfigured router IP address'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
