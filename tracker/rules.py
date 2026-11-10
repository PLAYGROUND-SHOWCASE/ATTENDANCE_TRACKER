from django.utils import timezone
from .models import Attendance, AuditLog, LaptopActivityLog, OutsideOfficeLog, InternetStatusLog, RouterPresenceLog

def enforce_checkout_rules(profile, time_passed_minutes=0):
    """
    Evaluates connection pings and simulator inputs to enforce the 7 Auto-Checkout Rules.
    If checkouts are triggered, logs them to the audit tables and sets employee presence to OFFLINE or CHECKED_OUT.
    
    Includes constraints:
    - Both phone AND laptop must be connected to office WiFi.
    - Distance between phone and laptop must not exceed 10 meters (otherwise considered OUTSIDE office range).
    - Checks 8-hour daily work duration targets.
    """
    sim_state = profile.sim_state
    
    # Check dual-device connection and distance constraint
    is_in_office_wifi = sim_state.wifi_connected and sim_state.phone_connected and (sim_state.phone_laptop_distance <= 10.0)
    
    # 1. Update Sim state timers if time passed
    if time_passed_minutes > 0:
        if not is_in_office_wifi:
            sim_state.wifi_disconnect_duration += time_passed_minutes
            if not sim_state.phone_connected:
                sim_state.phone_disconnect_duration += time_passed_minutes
            else:
                sim_state.phone_disconnect_duration = 0
        else:
            sim_state.wifi_disconnect_duration = 0
            sim_state.phone_disconnect_duration = 0
            
        if not sim_state.internet_active:
            sim_state.internet_lost_duration += time_passed_minutes
        else:
            sim_state.internet_lost_duration = 0
            
        if not sim_state.browser_open:
            sim_state.browser_closed_duration += time_passed_minutes
        else:
            sim_state.browser_closed_duration = 0
            
        if sim_state.laptop_state == 'SLEEP':
            sim_state.laptop_sleep_duration += time_passed_minutes
        else:
            sim_state.laptop_sleep_duration = 0
            
        if sim_state.laptop_state == 'IDLE':
            sim_state.idle_duration += time_passed_minutes
        elif sim_state.laptop_state == 'ACTIVE':
            sim_state.idle_duration = 0
            
        sim_state.save()

    # Get active attendance
    today = timezone.localdate()
    attendance = Attendance.objects.filter(employee=profile, date=today, check_out__isnull=True).first()
    
    if not attendance:
        if profile.current_status != 'CHECKED_OUT':
            profile.current_status = 'CHECKED_OUT'
            profile.save()
        return False, "Not checked in"

    checkout_triggered = False
    reason_code = ""
    message = "Checked in and working"

    # -- Rule 3: Laptop Shutdown (Immediate) --
    if sim_state.laptop_state == 'OFF':
        checkout_triggered = True
        reason_code = "LAPTOP_SHUTDOWN"
        message = "Auto-checkout triggered: Laptop shutdown detected."

    # -- Rule 1: Internet Offline (10 Minutes) --
    elif not sim_state.internet_active and sim_state.internet_lost_duration >= 10:
        checkout_triggered = True
        reason_code = "INTERNET_LOST"
        message = "Auto-checkout triggered: Internet lost for 10+ minutes."

    # -- Rule 2: WiFi Router Disconnected (15 Minutes) --
    elif not is_in_office_wifi and sim_state.wifi_disconnect_duration >= 15:
        checkout_triggered = True
        reason_code = "ROUTER_DISCONNECT"
        if not sim_state.wifi_connected:
            message = "Auto-checkout triggered: Laptop WiFi connection lost for 15+ minutes."
        elif not sim_state.phone_connected:
            message = "Auto-checkout triggered: Phone WiFi connection lost for 15+ minutes."
        else:
            message = "Auto-checkout triggered: Phone-to-laptop distance exceeded 10m limit for 15+ minutes."

    # -- Rule 4: Laptop Sleep (15 Minutes) --
    elif sim_state.laptop_state == 'SLEEP' and sim_state.laptop_sleep_duration >= 15:
        checkout_triggered = True
        reason_code = "LAPTOP_SLEEP"
        message = "Auto-checkout triggered: Laptop sleep mode active for 15+ minutes."

    # -- Rule 5: Browser Closed (10 Minutes) --
    elif not sim_state.browser_open and sim_state.browser_closed_duration >= 10:
        checkout_triggered = True
        reason_code = "BROWSER_CLOSED"
        message = "Auto-checkout triggered: Dashboard portal closed for 10+ minutes."

    # -- Rule 6: Idle Inactivity (30 Minutes) --
    elif sim_state.idle_duration >= 30:
        checkout_triggered = True
        reason_code = "IDLE_TIMEOUT"
        message = "Auto-checkout triggered: No keyboard/mouse inputs for 30+ minutes."

    # Perform Checkout if any rule triggered
    if checkout_triggered:
        now = timezone.now()
        attendance.check_out = now
        attendance.check_out_method = 'LAPTOP_AGENT'
        
        # Calculate total duration in hours
        duration = (now - attendance.check_in).total_seconds() / 3600.0
        attendance.total_hours = max(0.1, round(duration, 2))
        attendance.save()

        # Update profile state
        profile.current_status = 'OFFLINE'
        profile.save()

        # Log appropriate entries
        AuditLog.objects.create(
            user=profile.user,
            action="AUTO_CHECKOUT",
            details=message,
            ip_address=profile.last_seen_ip
        )

        if reason_code == "INTERNET_LOST":
            InternetStatusLog.objects.create(
                employee=profile,
                offline_start=now - timezone.timedelta(minutes=sim_state.internet_lost_duration),
                online_return=now,
                duration_seconds=sim_state.internet_lost_duration * 60,
                auto_checkout_triggered=True
            )
        elif reason_code == "ROUTER_DISCONNECT":
            OutsideOfficeLog.objects.create(
                employee=profile,
                out_time=now - timezone.timedelta(minutes=sim_state.wifi_disconnect_duration),
                return_time=now,
                duration_seconds=sim_state.wifi_disconnect_duration * 60,
                reason="Office Network/Distance Timeout"
            )
        elif reason_code == "LAPTOP_SHUTDOWN" or reason_code == "LAPTOP_SLEEP":
            LaptopActivityLog.objects.create(
                employee=profile,
                state='OFF' if reason_code == "LAPTOP_SHUTDOWN" else 'SLEEP',
                idle_duration_seconds=sim_state.laptop_sleep_duration * 60,
                cpu_usage=0.0
            )

        # Reset sim state outage trackers
        sim_state.wifi_disconnect_duration = 0
        sim_state.internet_lost_duration = 0
        sim_state.browser_closed_duration = 0
        sim_state.laptop_sleep_duration = 0
        sim_state.idle_duration = 0
        sim_state.save()

        return True, message

    # 3. If no checkout triggered, update current employee state
    old_status = profile.current_status
    
    if not is_in_office_wifi:
        profile.current_status = 'OUTSIDE'
    elif not sim_state.internet_active:
        profile.current_status = 'OFFLINE'
    elif sim_state.laptop_state == 'SLEEP':
        profile.current_status = 'OFFLINE'
    elif sim_state.laptop_state == 'LOCK':
        profile.current_status = 'IDLE'
    elif sim_state.idle_duration >= 10:
        profile.current_status = 'IDLE'
    else:
        if profile.current_status not in ['WORKING', 'MEETING']:
            profile.current_status = 'WORKING'

    if old_status != profile.current_status:
        profile.last_status_change = timezone.now()
        profile.save()
        
        # Log Audit event for status changes
        AuditLog.objects.create(
            user=profile.user,
            action="STATUS_CHANGE",
            details=f"Status transitioned from {old_status} to {profile.current_status} (Phone dist: {sim_state.phone_laptop_distance}m)",
            ip_address=profile.last_seen_ip
        )

    # 4. Accumulate daily hours if time passed
    if time_passed_minutes > 0:
        hours = time_passed_minutes / 60.0
        if profile.current_status == 'WORKING':
            profile.working_hours_today += hours
        elif profile.current_status == 'IDLE':
            profile.idle_hours_today += hours
        elif profile.current_status == 'OUTSIDE':
            profile.outside_hours_today += hours
        else:
            profile.break_hours_today += hours
        profile.save()

    # Compliance warning message for 9-hour target
    if profile.working_hours_today >= 9.0:
        message = f"Status updated to: {profile.current_status} | Compliance: 9-Hour target achieved!"
    else:
        rem = 9.0 - profile.working_hours_today
        message = f"Status updated to: {profile.current_status} | Compliance: Under 9 hours ({rem:.1f}h remaining)"

    return False, message
