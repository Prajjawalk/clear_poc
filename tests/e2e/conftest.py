"""Pytest configuration and fixtures for E2E tests."""

import os

import pytest

# Set environment variable to allow sync operations in async context
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.utils import timezone

from alerts.models import Alert, ShockType
from data_pipeline.models import Source
from location.models import AdmLevel, Location


@pytest.fixture(scope="session", autouse=True)
def configure_vite_for_tests():
    """Configure Django-Vite to use built assets instead of dev server."""
    from django.conf import settings

    # Override Vite configuration to use production mode
    settings.DJANGO_VITE["default"]["dev_mode"] = False

    yield


# Collect static files before E2E tests run
@pytest.fixture(scope="session", autouse=True)
def collect_static_files():
    """Run collectstatic before E2E tests to ensure static files are available."""
    import shutil
    from pathlib import Path

    from django.core.management import call_command

    # Check if static files already exist and are up to date
    static_root = Path(__file__).parent.parent.parent / "staticfiles_test"
    manifest_path = static_root / "staticfiles.json"

    # Only run collectstatic if manifest doesn't exist or is older than source files
    should_collect = True
    if manifest_path.exists():
        # Check if any source files are newer than manifest
        static_source = Path(__file__).parent.parent.parent / "static"
        if static_source.exists():
            manifest_mtime = manifest_path.stat().st_mtime
            source_files = list(static_source.rglob("*"))
            if source_files:
                newest_source = max((f.stat().st_mtime for f in source_files if f.is_file()), default=0)
                should_collect = newest_source > manifest_mtime
            else:
                should_collect = False

    if should_collect:
        # Clear existing collected static files
        if static_root.exists():
            shutil.rmtree(static_root)

        # Run collectstatic
        call_command("collectstatic", "--noinput", verbosity=0)

    yield

    # Cleanup after tests
    if static_root.exists():
        shutil.rmtree(static_root)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure browser launch arguments."""
    return {
        **browser_type_launch_args,
        "headless": True,  # Run in headless mode
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for all tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "Africa/Khartoum",
    }


@pytest.fixture(scope="function")
def page(context, base_url):
    """Override default page fixture to capture console messages."""
    page = context.new_page()

    # Only enable logging if DEBUG_E2E environment variable is set
    if os.getenv("DEBUG_E2E"):
        # Capture console messages
        def log_console_msg(msg):
            print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}")
            # Also log URL for resource loading failures
            if "Failed to load resource" in msg.text:
                print(f"  Location: {msg.location}")

        page.on("console", log_console_msg)

        # Capture page errors
        def log_page_error(error):
            print(f"BROWSER ERROR: {error}")

        page.on("pageerror", log_page_error)

        # Capture failed requests
        def log_request_failed(request):
            if request.failure:
                print(f"REQUEST FAILED: {request.url} - {request.failure}")

        page.on("requestfailed", log_request_failed)

    yield page

    page.close()


@pytest.fixture(scope="function")
def test_user(db):
    """Create a test user for authentication."""
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        is_staff=True,
        is_superuser=False
    )
    return user


@pytest.fixture(scope="function")
def admin_user(db):
    """Create an admin user."""
    user = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpass123"
    )
    return user


@pytest.fixture(scope="function")
def test_location(db):
    """Create a test location in Sudan."""
    admin_level = AdmLevel.objects.create(
        code="ADMIN1",
        name="State Level"
    )

    location = Location.objects.create(
        name="Khartoum",
        geo_id="SD001",
        admin_level=admin_level,
        point=Point(32.5599, 15.5007)  # Khartoum coordinates
    )
    return location


@pytest.fixture(scope="function")
def test_shock_types(db):
    """Create test shock types."""
    conflict = ShockType.objects.create(
        name="Conflict",
        icon="⚔️",
        color="#ff0000",
        css_class="bg-danger"
    )

    flood = ShockType.objects.create(
        name="Flood",
        icon="🌊",
        color="#0000ff",
        css_class="bg-primary"
    )

    return {"conflict": conflict, "flood": flood}


@pytest.fixture(scope="function")
def test_source(db):
    """Create a test data source."""
    source = Source.objects.create(
        name="Test Source",
        description="Test data source for E2E tests",
        is_active=True
    )
    return source


@pytest.fixture(scope="function")
def test_alerts(db, test_location, test_shock_types, test_source):
    """Create test alerts."""
    now = timezone.now()

    alert1 = Alert.objects.create(
        title="Conflict in Khartoum",
        text="Armed conflict reported in central Khartoum. Multiple casualties.",
        shock_type=test_shock_types["conflict"],
        severity=5,
        data_source=test_source,
        shock_date=(now - timedelta(days=1)).date(),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        go_no_go=True
    )
    alert1.locations.add(test_location)

    alert2 = Alert.objects.create(
        title="Flood Warning",
        text="Heavy rains causing flooding in low-lying areas.",
        shock_type=test_shock_types["flood"],
        severity=3,
        data_source=test_source,
        shock_date=(now - timedelta(hours=12)).date(),
        valid_from=now - timedelta(hours=12),
        valid_until=now + timedelta(days=7),
        go_no_go=True
    )
    alert2.locations.add(test_location)

    return [alert1, alert2]


@pytest.fixture(scope="class")
def authenticated_context(context, live_server, test_user):
    """Create an authenticated browser context (reusable across a test class)."""
    # Create a new page for login
    page = context.new_page()

    # Navigate to login page
    page.goto(f"{live_server.url}/auth/login/")

    # Fill in login form
    page.fill('input[name="username"]', "testuser")
    page.fill('input[name="password"]', "testpass123")

    # Submit form
    page.click('button[type="submit"]')

    # Wait for login to complete (check for redirect or specific element)
    page.wait_for_selector("body", timeout=5000)

    page.close()

    # Return the context which now has authenticated cookies
    return context


@pytest.fixture(scope="function")
def authenticated_page(page, live_server, test_user):
    """Create an authenticated browser page (simple login approach)."""
    # Navigate to login page
    page.goto(f"{live_server.url}/auth/login/")

    # Fill in login form and submit
    page.fill('input[name="username"]', "testuser")
    page.fill('input[name="password"]', "testpass123")

    # Click and wait for URL to change (fastest way to confirm login)
    with page.expect_navigation():
        page.click('button[type="submit"]')

    return page


@pytest.fixture(scope="function")
def admin_page(page, live_server, admin_user):
    """Create an authenticated admin browser page."""
    # Navigate to login page
    page.goto(f"{live_server.url}/auth/login/")

    # Fill in login form and submit
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "adminpass123")

    # Click and wait for URL to change (fastest way to confirm login)
    with page.expect_navigation():
        page.click('button[type="submit"]')

    return page


# Helper functions for E2E tests

def wait_for_map_ready(page, map_selector="#map"):
    """Wait for Leaflet map to be fully initialized."""
    page.wait_for_selector(f"{map_selector}", timeout=10000)
    page.wait_for_function(
        f"document.querySelector('{map_selector}') !== null && "
        f"document.querySelector('{map_selector}._leaflet_id') !== undefined",
        timeout=10000
    )


def wait_for_markers(page, min_count=1):
    """Wait for map markers to appear."""
    page.wait_for_selector(".leaflet-marker-icon", timeout=10000)
    page.wait_for_function(
        f"document.querySelectorAll('.leaflet-marker-icon').length >= {min_count}",
        timeout=10000
    )


def take_screenshot(page, name):
    """Take a screenshot for debugging."""
    page.screenshot(path=f"tests/e2e/screenshots/{name}.png")
