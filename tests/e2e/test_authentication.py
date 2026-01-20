"""E2E tests for authentication and navigation."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.django_db
def test_login_page_loads(page: Page, live_server):
    """Test that login page loads correctly."""
    page.goto(f"{live_server.url}/auth/login/")

    # Check for login form elements
    username_input = page.locator("input[name='username']")
    password_input = page.locator("input[name='password']")
    submit_button = page.locator("button[type='submit']")

    expect(username_input).to_be_visible()
    expect(password_input).to_be_visible()
    expect(submit_button).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_login_with_valid_credentials(page: Page, live_server, test_user):
    """Test logging in with valid credentials."""
    page.goto(f"{live_server.url}/auth/login/")

    # Fill in credentials
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "testpass123")

    # Submit form
    page.click("button[type='submit']")

    # Wait for navigation
    page.wait_for_load_state("networkidle")

    # Should be redirected away from login page
    # (exact destination depends on LOGIN_REDIRECT_URL)
    assert "/auth/login/" not in page.url


@pytest.mark.e2e
@pytest.mark.django_db
def test_login_with_invalid_credentials(page: Page, live_server):
    """Test that invalid login shows error."""
    page.goto(f"{live_server.url}/auth/login/")

    # Fill in invalid credentials
    page.fill("input[name='username']", "wronguser")
    page.fill("input[name='password']", "wrongpass")

    # Submit form
    page.click("button[type='submit']")

    # Wait a moment
    page.wait_for_timeout(1000)

    # Should still be on login page or show error
    assert "/auth/login/" in page.url or page.locator(".alert-danger, .error").count() > 0


@pytest.mark.e2e
@pytest.mark.django_db
def test_homepage_loads(page: Page, live_server):
    """Test that homepage loads."""
    page.goto(live_server.url)

    # Wait for page load
    page.wait_for_load_state("networkidle")

    # Should see some content
    body = page.locator("body")
    expect(body).to_be_visible()

    # Check for NRC branding
    nrc_elements = page.locator(".nrc-header, [class*='nrc'], img[alt*='NRC']")
    # Should have at least one NRC-branded element
    assert nrc_elements.count() > 0


@pytest.mark.e2e
@pytest.mark.django_db
def test_navigation_menu_exists(page: Page, live_server, test_user):
    """Test that navigation menu is present."""
    # Login first to access authenticated pages
    page.goto(f"{live_server.url}/auth/login/")
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "testpass123")
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    # Now navigate to homepage
    page.goto(live_server.url)
    page.wait_for_load_state("networkidle")

    # Look for navigation elements - be more flexible with selectors
    nav = page.locator("nav, .navbar, header, #navbar, .nav")
    assert nav.count() > 0, "No navigation found"


@pytest.mark.e2e
@pytest.mark.django_db
def test_responsive_mobile_view(page: Page, live_server):
    """Test that site works in mobile viewport."""
    # Set mobile viewport
    page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE

    page.goto(live_server.url)
    page.wait_for_load_state("networkidle")

    # Page should load without errors
    body = page.locator("body")
    expect(body).to_be_visible()

    # Check if hamburger menu appears (common mobile pattern)
    mobile_toggle = page.locator(".navbar-toggler, .mobile-menu-toggle, [data-toggle='collapse']")

    # If mobile toggle exists, it should be visible
    if mobile_toggle.count() > 0:
        expect(mobile_toggle.first).to_be_visible()
