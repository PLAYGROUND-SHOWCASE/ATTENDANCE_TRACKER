document.addEventListener('DOMContentLoaded', () => {
    // Theme Management
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        // Load preference
        if (localStorage.getItem('theme') === 'light') {
            document.body.classList.add('light-theme');
            themeBtn.innerText = '🌙';
        } else {
            themeBtn.innerText = '☀️';
        }

        themeBtn.addEventListener('click', () => {
            document.body.classList.toggle('light-theme');
            if (document.body.classList.contains('light-theme')) {
                localStorage.setItem('theme', 'light');
                themeBtn.innerText = '🌙';
            } else {
                localStorage.setItem('theme', 'dark');
                themeBtn.innerText = '☀️';
            }
        });
    }

    // Dynamic Live Dashboard Polling
    const liveMonitorTable = document.getElementById('live-monitor-tbody');
    const systemStatsSection = document.getElementById('system-stats-grid');
    
    if (liveMonitorTable || systemStatsSection) {
        // Poll every 4 seconds to simulate real-time socket updates
        setInterval(refreshDashboardData, 4000);
    }
});

// Refresh functions
async function refreshDashboardData() {
    try {
        const response = await fetch('/api/dashboard/stats/');
        if (!response.ok) return;
        const data = await response.json();
        
        // Update stats widgets
        updateStatValue('count-total', data.stats.total);
        updateStatValue('count-working', data.stats.working);
        updateStatValue('count-idle', data.stats.idle);
        updateStatValue('count-outside', data.stats.outside);
        updateStatValue('count-offline', data.stats.offline);
        updateStatValue('count-checkedout', data.stats.checked_out);

        // Update live table
        const tbody = document.getElementById('live-monitor-tbody');
        if (tbody && data.employees) {
            tbody.innerHTML = '';
            data.employees.forEach(emp => {
                const statusBadge = getStatusBadgeHTML(emp.status);
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${emp.name}</strong><br><small style="color:var(--text-muted)">${emp.employee_id}</small></td>
                    <td>${statusBadge}</td>
                    <td><code style="font-size:0.85rem">${emp.mac || '-'}</code></td>
                    <td>${emp.ip || '-'}</td>
                    <td>${emp.duration || '0m'}</td>
                    <td>${emp.today_hours.toFixed(1)}h / ${emp.idle_hours.toFixed(1)}h</td>
                    <td>
                        <a href="/employee/${emp.id}/" class="btn btn-secondary" style="padding:4px 8px; font-size:0.75rem;">View Profile</a>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error('Error polling dashboard stats:', e);
    }
}

function updateStatValue(elementId, value) {
    const el = document.getElementById(elementId);
    if (el) {
        el.innerText = value;
    }
}

function getStatusBadgeHTML(status) {
    let dotColor = 'offline';
    let text = 'Offline';
    
    if (status === 'WORKING') { dotColor = 'working'; text = 'Working'; }
    else if (status === 'IDLE') { dotColor = 'idle'; text = 'Idle'; }
    else if (status === 'MEETING') { dotColor = 'meeting'; text = 'Meeting'; }
    else if (status === 'OUTSIDE') { dotColor = 'outside'; text = 'Outside Office'; }
    else if (status === 'OFFLINE') { dotColor = 'offline'; text = 'Offline'; }
    else if (status === 'CHECKED_OUT') { dotColor = 'checked_out'; text = 'Checked Out'; }

    return `<span class="badge status-${status.toLowerCase()}"><span class="badge-dot"></span>${text}</span>`;
}

// Simulation triggering helper
async function triggerSimulationEvent(employeeId, action, extraParams = {}) {
    const btn = event?.target;
    if (btn) {
        btn.disabled = true;
        btn.dataset.originalText = btn.innerText;
        btn.innerText = 'Triggering...';
    }

    try {
        const response = await fetch('/api/simulator/event/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                employee_id: employeeId,
                action: action,
                ...extraParams
            })
        });

        const result = await response.json();
        
        // Show notification or alert toast
        showSimulationNotification(result.message, result.success ? 'success' : 'error');
        
        // Refresh page tables/logs or stats
        if (window.location.pathname.includes('/simulator/')) {
            setTimeout(() => {
                window.location.reload();
            }, 1200);
        } else {
            refreshDashboardData();
        }
    } catch (e) {
        console.error('Simulation error:', e);
        showSimulationNotification('Failed to connect to simulator API', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = btn.dataset.originalText;
        }
    }
}

function showSimulationNotification(msg, type = 'success') {
    const notifyContainer = document.getElementById('notification-container');
    if (!notifyContainer) {
        const div = document.createElement('div');
        div.id = 'notification-container';
        div.style.position = 'fixed';
        div.style.bottom = '20px';
        div.style.right = '20px';
        div.style.zIndex = '1000';
        div.style.display = 'flex';
        div.style.flexDirection = 'column';
        div.style.gap = '10px';
        document.body.appendChild(div);
    }
    
    const container = document.getElementById('notification-container');
    const toast = document.createElement('div');
    toast.className = 'card';
    toast.style.padding = '12px 20px';
    toast.style.borderLeft = `4px solid ${type === 'success' ? 'var(--state-working)' : 'var(--state-offline)'}`;
    toast.style.backgroundColor = 'var(--bg-surface)';
    toast.style.fontSize = '0.9rem';
    toast.style.boxShadow = 'var(--shadow-lg)';
    toast.style.minWidth = '250px';
    toast.innerText = msg;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'opacity 0.4s, transform 0.4s';
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// CSRF cookie parsing
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// --- PROJECT MANAGEMENT & ORGANIZATION JS ACTIONS ---

// Modal helpers
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('open');
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('open');
    }
}

// Tab switcher helper
document.addEventListener('DOMContentLoaded', () => {
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            
            // If it's a dashboard tab, update URL parameter and reload or filter
            const isDashboard = btn.closest('.tab-nav')?.dataset.type === 'dashboard';
            if (isDashboard) {
                const url = new URL(window.location);
                url.searchParams.set('tab', tabId);
                window.location.href = url.toString();
                return;
            }
            
            // Otherwise local tab switch
            const parent = btn.closest('.tab-container') || document;
            parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            parent.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            const targetPane = document.getElementById(`tab-pane-${tabId}`);
            if (targetPane) {
                targetPane.classList.add('active');
            }
        });
    });
});

// Kanban Card quick move/dropdown status change
async function moveKanbanIssue(issueId, newStatus, projectId) {
    try {
        const response = await fetch(`/api/issue/${issueId}/status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ status: newStatus })
        });
        const res = await response.json();
        if (res.success) {
            showSimulationNotification('Task status updated successfully', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        } else {
            showSimulationNotification(res.message || 'Failed to update task', 'error');
        }
    } catch(e) {
        console.error('Error shifting task status:', e);
        showSimulationNotification('Network error occurred updating task', 'error');
    }
}

// User Skills management via AJAX
async function addEmployeeSkill(profileId) {
    const nameInput = document.getElementById('new-skill-name');
    const profSelect = document.getElementById('new-skill-proficiency');
    if (!nameInput || !nameInput.value.trim()) return;
    
    try {
        const response = await fetch(`/users/${profileId}/skills/add/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                skill_name: nameInput.value.trim(),
                proficiency: profSelect ? profSelect.value : 'INTERMEDIATE'
            })
        });
        const res = await response.json();
        if (res.success) {
            showSimulationNotification('Skill added successfully', 'success');
            nameInput.value = '';
            setTimeout(() => {
                window.location.reload();
            }, 800);
        } else {
            showSimulationNotification(res.message, 'error');
        }
    } catch(e) {
        console.error('Error adding skill:', e);
    }
}

async function removeEmployeeSkill(profileId, skillId) {
    if (!confirm('Are you sure you want to remove this skill?')) return;
    try {
        const response = await fetch(`/users/${profileId}/skills/delete/${skillId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        const res = await response.json();
        if (res.success) {
            showSimulationNotification('Skill removed', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 800);
        } else {
            showSimulationNotification(res.message, 'error');
        }
    } catch(e) {
        console.error('Error deleting skill:', e);
    }
}

