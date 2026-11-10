import os
import glob
import subprocess
import time
import socket
from playwright.sync_api import sync_playwright

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def clean_screenshots():
    print("Clearing old screenshots...")
    os.makedirs("screenshots", exist_ok=True)
    files = glob.glob(r"screenshots\*.png")
    for f in files:
        try:
            os.remove(f)
            print(f"Deleted: {f}")
        except Exception as e:
            print(f"Failed to delete {f}: {e}")

def run_screenshot_flow():
    # 1. Clean the database first
    print("Resetting database to seed state...")
    subprocess.run(["python", "manage.py", "seed_data"], check=True)

    # 2. Start django server
    print("Starting Django server on port 8000...")
    server_process = subprocess.Popen(
        ["python", "manage.py", "runserver", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # Wait for port to open (up to 15 seconds)
        for i in range(15):
            if is_port_open(8000):
                print("Server is up and running on port 8000.")
                break
            time.sleep(1)
        else:
            raise Exception("Timeout waiting for Django server to start on port 8000")

        # Give the server an extra second to initialize
        time.sleep(1)

        # 3. Take screenshots using Playwright
        with sync_playwright() as p:
            print("Launching browser...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            # 3.1. Login Page
            print("Capturing Login page...")
            page.goto("http://localhost:8000/login/")
            # Wait for content to load
            page.wait_for_selector("input#username")
            page.screenshot(path="screenshots/login_page.png")

            # 3.2. Register Page
            print("Capturing Register page...")
            page.goto("http://localhost:8000/register/")
            page.wait_for_selector("input#username")
            page.screenshot(path="screenshots/register_page.png")

            # 3.3. Log in as admin
            print("Logging in as admin...")
            page.goto("http://localhost:8000/login/")
            page.fill("input#username", "admin")
            page.fill("input#password", "admin")
            page.click("button[type='submit']")
            page.wait_for_url("**/dashboard/") # Should redirect to admin dashboard
            page.wait_for_selector(".user-pill") # Wait for base layout load

            # 3.4. Admin Dashboard Page
            print("Capturing Admin Dashboard page...")
            time.sleep(1) # Allow charts to render
            page.screenshot(path="screenshots/admin_dashboard.png")

            # 3.5. Employee Dashboard Page
            print("Capturing Employee Dashboard page...")
            page.goto("http://localhost:8000/portal/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/employee_dashboard.png")

            # 3.6. Check-in and Checkout Error page
            print("Checking in employee...")
            # Click check in button
            page.click("button:has-text('Check In Now')")
            page.wait_for_selector("button:has-text('Check Out Now')")
            
            print("Attempting checkout to trigger error...")
            # Click check out button (fails 9 hour validation)
            page.click("button:has-text('Check Out Now')")
            # Wait for page reload & message display
            page.wait_for_selector("div.card:has-text('Checkout Blocked')")
            page.screenshot(path="screenshots/employee_checkout_error.png")

            # 3.7. Dashboard Hub, Projects, Organization, Users, Expenses, Settings
            print("Capturing Dashboard Hub...")
            page.goto("http://localhost:8000/dashboard/hub/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/dashboard_hub.png")

            print("Capturing Projects List...")
            page.goto("http://localhost:8000/projects/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/projects_list.png")

            print("Capturing Organization Hub...")
            page.goto("http://localhost:8000/organization/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/organization_hub.png")

            print("Capturing Users & Teams...")
            page.goto("http://localhost:8000/users/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/users_teams.png")

            print("Capturing Expenses Tracker...")
            page.goto("http://localhost:8000/expenses/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/expenses_tracker.png")

            print("Capturing Portal Settings...")
            page.goto("http://localhost:8000/settings/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/portal_settings.png")

            # 3.8. Agent Simulator Page
            print("Capturing Agent Simulator page...")
            page.goto("http://localhost:8000/simulator/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/agent_simulator.png")

            # 3.9. Reports Page
            print("Capturing Reports page...")
            page.goto("http://localhost:8000/reports/")
            page.wait_for_selector(".user-pill")
            page.screenshot(path="screenshots/reports_logs.png")

            browser.close()
            print("All screenshots successfully captured!")

    finally:
        print("Stopping Django server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server stopped.")

if __name__ == "__main__":
    clean_screenshots()
    run_screenshot_flow()
