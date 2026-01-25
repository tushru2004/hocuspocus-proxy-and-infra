"""
Production VPN verification tests.

These tests verify that the VPN is working correctly against the PRODUCTION database.
No database switching or seeding - tests real production state.

Usage:
    pytest tests/e2e_prod/test_verify_vpn.py -v -s
    # Or via Makefile:
    make verify-vpn-appium
"""
import pytest
import time


class TestVPNVerification:
    """Verify VPN filtering is working in production."""

    @pytest.mark.timeout(60)
    def test_jre_video_allowed(self, ios_driver, mitmproxy_logs):
        """Test that Joe Rogan Experience videos are allowed."""
        print("\n📱 [TEST] Opening JRE video (should be allowed)...")

        # JRE test video
        video_url = "https://m.youtube.com/watch?v=lwgJhmsQz0U"
        ios_driver.get(video_url)

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

        print("✅ [TEST] JRE video ALLOWED (as expected)")

    @pytest.mark.timeout(60)
    def test_reddit_blocked(self, ios_driver, mitmproxy_logs):
        """Test that reddit.com is blocked (non-whitelisted domain)."""
        print("\n📱 [TEST] Opening reddit.com (should be blocked)...")

        # Add cache bust to ensure fresh request
        cache_bust = int(time.time())
        ios_driver.get(f"https://reddit.com/?_cb={cache_bust}")

        # Wait for request to be processed
        time.sleep(6)

        # Check proxy logs
        logs = mitmproxy_logs(tail=50)

        # Verify reddit was blocked
        blocked = (
            ("BLOCKING" in logs or "BLOCKED" in logs) and
            "reddit" in logs.lower()
        )
        generic_blocked = "BLOCKING non-whitelisted domain" in logs or "BLOCKED" in logs

        assert blocked or generic_blocked, \
            f"reddit.com was not blocked! Expected BLOCKING or BLOCKED in logs."

        print("✅ [TEST] reddit.com BLOCKED (as expected)")

    @pytest.mark.timeout(30)
    def test_google_allowed(self, ios_driver, mitmproxy_logs):
        """Test that google.com is allowed (whitelisted domain)."""
        print("\n📱 [TEST] Opening google.com (should be allowed)...")

        cache_bust = int(time.time())
        ios_driver.get(f"https://www.google.com/?_cb={cache_bust}")

        time.sleep(5)

        logs = mitmproxy_logs(tail=30)

        # Verify google was allowed
        assert "Allowing whitelisted domain" in logs or "google.com" in logs, \
            "google.com request not found in logs"

        # Make sure it wasn't blocked
        assert "BLOCKING.*google.com" not in logs, \
            "google.com was blocked but should be allowed!"

        print("✅ [TEST] google.com ALLOWED (as expected)")


class TestLocationWhitelist:
    """Test per-location whitelist feature.

    NOTE: These tests only work when physically at a blocked location
    with the appropriate whitelist configured. Current setup:
    - Blocked location: "The Social Hub Vienna"
    - Per-location whitelist: cnbc.com
    """

    @pytest.mark.timeout(90)
    def test_location_whitelisted_domain_allowed(self, ios_driver, mitmproxy_logs):
        """Test that domain in per-location whitelist is allowed at blocked location.

        Prerequisites:
        - User must be at "The Social Hub Vienna" (or other blocked location)
        - cnbc.com must be in the per-location whitelist for that location
        """
        print("\n📱 [TEST] Testing per-location whitelist...")
        print("     Prerequisites: Must be at blocked location with cnbc.com whitelisted")

        # First, visit a non-whitelisted site to trigger location tracking
        cache_bust = int(time.time())
        ios_driver.get(f"https://reddit.com/?_cb={cache_bust}")
        time.sleep(8)  # Wait for location tracking to complete

        # Check if we're at a blocked location
        logs = mitmproxy_logs(tail=50)
        at_blocked_location = "BLOCKING ENABLED - At blocked location" in logs or "BLOCKED at The Social Hub" in logs

        if not at_blocked_location:
            pytest.skip("Not at a blocked location - skipping per-location whitelist test")

        print("✅ Confirmed at blocked location - testing whitelist...")

        # Now test cnbc.com which should be in the per-location whitelist
        cache_bust = int(time.time())
        ios_driver.get(f"https://www.cnbc.com/?_cb={cache_bust}")
        time.sleep(8)

        logs = mitmproxy_logs(tail=100)

        # Verify cnbc.com was allowed via per-location whitelist
        whitelist_allowed = "ALLOWING" in logs and "cnbc" in logs.lower() and "per-location whitelist" in logs

        assert whitelist_allowed, \
            f"cnbc.com was not allowed via per-location whitelist! Check logs:\n{logs[-500:]}"

        print("✅ [TEST] cnbc.com ALLOWED via per-location whitelist (as expected)")

    @pytest.mark.timeout(60)
    def test_non_whitelisted_domain_blocked_at_location(self, ios_driver, mitmproxy_logs):
        """Test that non-whitelisted domains are blocked at blocked location."""
        print("\n📱 [TEST] Testing that non-whitelisted domain is blocked at blocked location...")

        cache_bust = int(time.time())
        ios_driver.get(f"https://reddit.com/?_cb={cache_bust}")
        time.sleep(8)

        logs = mitmproxy_logs(tail=50)

        # Check if blocked at location (not just domain blocking)
        blocked_at_location = "BLOCKED at The Social Hub" in logs or "BLOCKED - At" in logs

        if not blocked_at_location:
            # Check if we got regular domain blocking instead
            if "BLOCKING non-whitelisted domain" in logs:
                pytest.skip("Not at blocked location - got regular domain blocking instead")
            pytest.fail("reddit.com was not blocked!")

        print("✅ [TEST] reddit.com BLOCKED at blocked location (as expected)")


class TestVPNQuickCheck:
    """Quick smoke test for VPN - just verifies blocking works."""

    @pytest.mark.timeout(30)
    def test_domain_blocking_works(self, ios_driver, mitmproxy_logs):
        """Quick test that domain blocking is working."""
        print("\n📱 [QUICK] Testing domain blocking...")

        cache_bust = int(time.time())
        ios_driver.get(f"https://reddit.com/?_cb={cache_bust}")

        time.sleep(5)

        logs = mitmproxy_logs(tail=30)

        assert "BLOCKED" in logs or "BLOCKING" in logs, \
            "No blocking detected in logs - VPN filtering may not be working!"

        print("✅ [QUICK] Domain blocking is working")
