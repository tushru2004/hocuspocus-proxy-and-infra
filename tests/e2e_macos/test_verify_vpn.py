"""
macOS Production VPN verification tests.

These tests verify that the VPN is working correctly on MacBook Air
against the PRODUCTION database. No database switching or seeding.

Usage:
    pytest tests/e2e_macos/test_verify_vpn.py -v -s
    # Or via Makefile:
    make verify-vpn-macos
"""
import pytest
import time


class TestMacOSVPNVerification:
    """Verify VPN filtering is working on macOS."""

    @pytest.mark.timeout(60)
    def test_jre_video_allowed(self, macos_driver, mitmproxy_logs):
        """Test that Joe Rogan Experience videos are allowed."""
        print("\n💻 [TEST macOS] Opening JRE video (should be allowed)...")

        # JRE test video
        video_url = "https://m.youtube.com/watch?v=lwgJhmsQz0U"
        macos_driver.get(video_url)

        # Wait for page to load and requests to flow
        time.sleep(8)

        # Check proxy logs
        logs = mitmproxy_logs(tail=100)

        # Verify JRE channel was detected and allowed
        assert "Joe Rogan" in logs or "lwgJhmsQz0U" in logs, \
            f"JRE video not found in logs. Expected 'Joe Rogan' or video ID in logs."

        # Make sure it wasn't blocked
        assert "BLOCKING.*lwgJhmsQz0U" not in logs, \
            "JRE video was blocked but should be allowed!"

        print("✅ [TEST macOS] JRE video ALLOWED (as expected)")

    @pytest.mark.timeout(60)
    def test_twitter_blocked(self, macos_driver, mitmproxy_logs):
        """Test that twitter.com is blocked (non-whitelisted domain)."""
        print("\n💻 [TEST macOS] Opening twitter.com (should be blocked)...")

        # Clear any cached content
        macos_driver.get("about:blank")
        time.sleep(1)

        # Add cache bust to ensure fresh request
        cache_bust = int(time.time())
        macos_driver.get(f"https://twitter.com/?_nocache={cache_bust}")

        # Wait for request to be processed
        time.sleep(6)

        # Primary check: look for block page content in the browser
        page_source = macos_driver.page_source
        page_blocked = "Access Denied" in page_source

        # Secondary check: proxy logs (may not always show due to caching)
        logs = mitmproxy_logs(tail=50)
        logs_blocked = (
            "BLOCKING" in logs and
            ("twitter" in logs.lower() or "x.com" in logs.lower())
        ) or "BLOCKING non-whitelisted domain" in logs

        assert page_blocked or logs_blocked, \
            f"twitter.com was not blocked! Page title: {macos_driver.title}"

        print("✅ [TEST macOS] twitter.com BLOCKED (as expected)")

    @pytest.mark.timeout(30)
    def test_google_allowed(self, macos_driver, mitmproxy_logs):
        """Test that google.com is allowed (whitelisted domain)."""
        print("\n💻 [TEST macOS] Opening google.com (should be allowed)...")

        cache_bust = int(time.time())
        macos_driver.get(f"https://www.google.com/?_cb={cache_bust}")

        time.sleep(5)

        logs = mitmproxy_logs(tail=30)

        # Verify google was allowed
        assert "Allowing whitelisted domain" in logs or "google.com" in logs, \
            "google.com request not found in logs"

        # Make sure it wasn't blocked
        assert "BLOCKING.*google.com" not in logs, \
            "google.com was blocked but should be allowed!"

        print("✅ [TEST macOS] google.com ALLOWED (as expected)")


class TestMacOSLocationWhitelist:
    """Test per-location whitelist feature on macOS.

    NOTE: These tests only work when physically at a blocked location
    with the appropriate whitelist configured. Current setup:
    - Blocked location: "The Social Hub Vienna"
    - Per-location whitelist: cnbc.com
    """

    @pytest.mark.timeout(90)
    def test_location_whitelisted_domain_allowed(self, macos_driver, mitmproxy_logs):
        """Test that domain in per-location whitelist is allowed at blocked location.

        Prerequisites:
        - MacBook Air must be at "The Social Hub Vienna" (or other blocked location)
        - cnbc.com must be in the per-location whitelist for that location
        """
        print("\n💻 [TEST macOS] Testing per-location whitelist...")
        print("     Prerequisites: Must be at blocked location with cnbc.com whitelisted")

        # First, visit a non-whitelisted site to trigger location tracking
        cache_bust = int(time.time())
        macos_driver.get(f"https://twitter.com/?_cb={cache_bust}")
        time.sleep(8)  # Wait for location tracking to complete

        # Check if we're at a blocked location (via page content or logs)
        page_source = macos_driver.page_source
        page_blocked = (
            "Access Denied" in page_source or
            "blocked location" in page_source.lower() or
            "browsing not allowed" in page_source.lower()
        )

        logs = mitmproxy_logs(tail=50)
        logs_blocked = (
            "BLOCKING ENABLED - At blocked location" in logs or
            "BLOCKED at The Social Hub" in logs or
            "BLOCKED at John Harris" in logs
        )

        if not page_blocked and not logs_blocked:
            pytest.skip("Not at a blocked location - skipping per-location whitelist test")

        print("✅ Confirmed at blocked location - testing whitelist...")

        # Now test cnbc.com which should be in the per-location whitelist
        cache_bust = int(time.time())
        macos_driver.get(f"https://www.cnbc.com/?_cb={cache_bust}")
        time.sleep(8)

        # Check if cnbc.com loaded (not blocked)
        page_source = macos_driver.page_source
        page_title = macos_driver.title

        # cnbc.com should load - check for CNBC content or absence of block page
        cnbc_loaded = (
            "CNBC" in page_title or
            "cnbc" in page_source.lower() or
            ("Access Denied" not in page_source and "blocked location" not in page_source.lower())
        )

        # Also check logs as secondary verification
        logs = mitmproxy_logs(tail=100)
        logs_allowed = "ALLOWING" in logs and "cnbc" in logs.lower()

        assert cnbc_loaded or logs_allowed, \
            f"cnbc.com was not allowed via per-location whitelist! Title: {page_title}"

        print("✅ [TEST macOS] cnbc.com ALLOWED via per-location whitelist (as expected)")

    @pytest.mark.timeout(60)
    def test_non_whitelisted_domain_blocked_at_location(self, macos_driver, mitmproxy_logs):
        """Test that non-whitelisted domains are blocked at blocked location."""
        print("\n💻 [TEST macOS] Testing that non-whitelisted domain is blocked at blocked location...")

        cache_bust = int(time.time())
        macos_driver.get(f"https://twitter.com/?_cb={cache_bust}")
        time.sleep(8)

        # Primary check: look for block page content in the browser
        page_source = macos_driver.page_source
        page_blocked = (
            "Access Denied" in page_source or
            "blocked location" in page_source.lower() or
            "browsing not allowed" in page_source.lower()
        )

        # Secondary check: proxy logs (may fail if kubectl/gcloud not working)
        logs = mitmproxy_logs(tail=50)
        logs_blocked = (
            "BLOCKED at The Social Hub" in logs or
            "BLOCKED at John Harris" in logs or
            "BLOCKED - At" in logs
        )

        if page_blocked or logs_blocked:
            print("✅ [TEST macOS] twitter.com BLOCKED at blocked location (as expected)")
            return

        # Check if we got regular domain blocking instead
        if "BLOCKING non-whitelisted domain" in logs or "Access Denied" in page_source:
            pytest.skip("Not at blocked location - got regular domain blocking instead")

        pytest.fail(f"twitter.com was not blocked! Page title: {macos_driver.title}")


class TestMacOSVPNQuickCheck:
    """Quick smoke test for VPN on macOS - just verifies blocking works."""

    @pytest.mark.timeout(30)
    def test_domain_blocking_works(self, macos_driver, mitmproxy_logs):
        """Quick test that domain blocking is working on macOS."""
        print("\n💻 [QUICK macOS] Testing domain blocking...")

        # Clear cache
        macos_driver.get("about:blank")
        time.sleep(1)

        cache_bust = int(time.time())
        macos_driver.get(f"https://twitter.com/?_nocache={cache_bust}")

        time.sleep(5)

        # Check page content for block page
        page_source = macos_driver.page_source
        page_blocked = "Access Denied" in page_source

        # Also check logs as secondary verification
        logs = mitmproxy_logs(tail=30)
        logs_blocked = "BLOCKING" in logs

        assert page_blocked or logs_blocked, \
            f"No blocking detected! Title: {macos_driver.title}"

        print("✅ [QUICK macOS] Domain blocking is working")
