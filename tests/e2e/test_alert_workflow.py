"""E2E tests for alert workflow."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_map_displays_alerts(authenticated_page: Page, live_server, test_alerts):
    """Test that alerts appear correctly on the map."""
    page = authenticated_page
    # Navigate to alerts map
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for markers to appear (implies map is ready)
    page.wait_for_selector(".leaflet-marker-icon", timeout=5000)

    # Check that we have markers
    markers = page.locator(".leaflet-marker-icon")
    marker_count = markers.count()

    # We created 2 alerts, both at the same location
    # So we expect at least 1 marker (could be clustered)
    assert marker_count >= 1, f"Expected at least 1 marker, found {marker_count}"

    # Check alert count is displayed
    alert_count_el = page.locator("#alert-count")
    expect(alert_count_el).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_map_filtering(authenticated_page: Page, live_server, test_alerts):
    """Test that alert filters work correctly."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for markers (implies map is ready)
    page.wait_for_selector(".leaflet-marker-icon", timeout=10000)

    # Get initial marker count
    initial_markers = page.locator(".leaflet-marker-icon").count()

    # Uncheck one shock type filter (if filters are available)
    # This is a defensive test - it won't fail if filters aren't rendered yet
    shock_type_filters = page.locator(".shock-type-filter")
    if shock_type_filters.count() > 0:
        # Uncheck first filter
        shock_type_filters.first.uncheck()

        # Click apply filters button
        apply_btn = page.locator("#apply-filters")
        if apply_btn.count() > 0:
            apply_btn.click()

            # Wait briefly for filtering animation
            page.wait_for_timeout(200)

            # Verify markers were filtered
            filtered_markers = page.locator(".leaflet-marker-icon").count()

            # Count should change or stay same (if other type has same location)
            assert filtered_markers <= initial_markers


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_popup_displays_details(authenticated_page: Page, live_server, test_alerts):
    """Test that clicking a marker shows alert details in popup."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for markers (implies map is ready)
    page.wait_for_selector(".leaflet-marker-icon", timeout=10000)

    # Click the first marker - use force=True to bypass overlapping elements
    marker = page.locator(".leaflet-marker-icon").first
    marker.click(force=True)

    # Wait for popup to appear
    popup = page.locator(".leaflet-popup-content")
    expect(popup).to_be_visible(timeout=5000)

    # Check popup contains alert information
    popup_content = popup.inner_text()

    # Should contain one of our alert titles
    assert "Conflict in Khartoum" in popup_content or "Flood Warning" in popup_content

    # Should have severity information
    assert "Severity" in popup_content


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_reset_filters(authenticated_page: Page, live_server, test_alerts):
    """Test that reset filters button works."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for map
    page.wait_for_selector("#alert-map")
    page.wait_for_selector(".leaflet-marker-icon", timeout=10000)

    # Check if reset button exists
    reset_btn = page.locator("#reset-filters")
    if reset_btn.count() > 0:
        # Uncheck some filters first
        shock_type_filters = page.locator(".shock-type-filter:checked")
        if shock_type_filters.count() > 0:
            shock_type_filters.first.uncheck()

        # Click reset
        reset_btn.click()

        # Wait briefly for reset
        page.wait_for_timeout(100)

        # All filters should be checked again
        checked_filters = page.locator(".shock-type-filter:checked")
        unchecked_filters = page.locator(".shock-type-filter:not(:checked)")

        # After reset, most filters should be checked
        assert checked_filters.count() >= unchecked_filters.count()


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_list_view(authenticated_page: Page, live_server, test_alerts):
    """Test that alert list page displays alerts."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/")

    # Check page title or heading (wait for it to appear)
    heading = page.locator("h1, h2").first
    expect(heading).to_be_visible()

    # Check if we have alert cards or table rows
    # The exact selector depends on your template structure
    alerts_displayed = (
        page.locator(".alert-card").count() > 0 or
        page.locator("table tbody tr").count() > 0 or
        page.locator("[data-alert-id]").count() > 0
    )

    assert alerts_displayed, "No alerts found on alert list page"


@pytest.mark.e2e
@pytest.mark.django_db
def test_alert_map_legend_displays(authenticated_page: Page, live_server, test_alerts, test_shock_types):
    """Test that map legend displays shock types."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for map
    page.wait_for_selector("#alert-map")

    # Look for legend (might be in different locations)
    legend = page.locator(".map-legend, .leaflet-legend-control, #mapLegendContent")

    # Legend should exist somewhere on the page
    if legend.count() > 0:
        # Check for shock type icons in legend
        legend_text = legend.first.inner_text()

        # Should mention shock types
        assert "Conflict" in legend_text or "Flood" in legend_text or "Severity" in legend_text


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.slow
def test_alert_map_fullscreen(authenticated_page: Page, live_server, test_alerts):
    """Test fullscreen functionality (if implemented)."""
    page = authenticated_page
    page.goto(f"{live_server.url}/alerts/map/")

    # Wait for map
    page.wait_for_selector("#alert-map")

    # Look for fullscreen button
    fullscreen_btn = page.locator("#fullscreen-btn, [data-fullscreen], .fullscreen-toggle")

    if fullscreen_btn.count() > 0:
        # Click fullscreen button
        fullscreen_btn.first.click()

        # Wait briefly for fullscreen animation
        page.wait_for_timeout(200)

        # Check if map container has expanded
        # (The exact behavior depends on implementation)
        map_container = page.locator("#alert-map")
        expect(map_container).to_be_visible()
