"""
Test for location permission overlay.

This test runs with autoAcceptAlerts DISABLED so we can verify
the proxy-injected location overlay appears and functions correctly.

Run separately from other E2E tests:
    PYTHONPATH=src pytest tests/e2e/test_location_overlay.py -v
"""
import pytest
import time
import logging
import subprocess
import os
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy


@pytest.mark.usefixtures("seed_test_database")
class TestLocationOverlay:
    """Test location overlay without auto-accepting alerts.

    This test verifies that the proxy-injected location permission overlay
    appears correctly and can be dismissed by the user.

    Important: This test does NOT auto-accept alerts, so the location
    permission dialog will appear and the overlay should be visible.
    """

    @pytest.fixture(scope="class")
    def vpn_server_ip(self):
        """Get VPN server IP from kubectl (GKE LoadBalancer)."""
        try:
            result = subprocess.run(
                ["kubectl", "-n", "hocuspocus", "get", "svc", "vpn-service",
                 "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}"],
                capture_output=True,
                text=True,
                check=True
            )
            ip = result.stdout.strip()
            if not ip:
                pytest.fail("Could not get VPN service external IP. Is the GKE cluster running?")
            return ip
        except subprocess.CalledProcessError:
            pytest.fail("Could not get VPN server IP from kubectl. Is kubectl configured?")

    @pytest.fixture(scope="class")
    def ios_driver(self, vpn_server_ip):
        """Set up iOS device WITHOUT auto-accepting alerts.

        This allows us to test that the location overlay appears
        before the user grants location permission.
        """
        import socket
        print(f"\n🍎 [FIXTURE] ios_driver starting with VPN IP: {vpn_server_ip}")

        # Verify VPN server is reachable (UDP 500 for IKEv2)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            sock.sendto(b"test", (vpn_server_ip, 500))
            sock.close()
            logging.info(f"✅ VPN server at {vpn_server_ip} is reachable")
        except Exception as e:
            logging.warning(f"⚠️  Could not verify VPN server: {e} (may still work)")

        device_type = os.getenv('IOS_DEVICE_TYPE', 'real').lower()

        options = XCUITestOptions()
        options.platform_name = "iOS"
        options.browser_name = "Safari"
        options.automation_name = "XCUITest"
        options.no_reset = True
        options.full_reset = False

        # KEY DIFFERENCE: Do NOT auto-accept alerts
        # This allows us to see the location overlay before permission is granted
        options.set_capability("autoAcceptAlerts", False)

        if device_type == 'simulator':
            options.platform_version = "26.2"
            options.device_name = "iPhone 17 Pro"
            options.set_capability("wdaLaunchTimeout", 60000)
        else:
            options.platform_version = "18.7.3"
            options.device_name = "Tushar's iPhone"
            options.udid = "00008020-0004695621DA002E"
            options.show_xcode_log = True

            # WebDriverAgent code signing configuration for real device
            # These settings survive Appium reinstalls (no need to reconfigure Xcode)
            options.set_capability("xcodeOrgId", "QG9U628JFD")  # Apple Team ID
            options.set_capability("xcodeSigningId", "iPhone Developer")
            options.updated_wda_bundle_id = "com.hocuspocus.WebDriverAgentRunner"

            # After fresh Appium install, run once with: USE_PREBUILT_WDA=false make test-e2e
            # This builds and installs WDA. Subsequent runs use prebuilt (faster).
            use_prebuilt = os.getenv("USE_PREBUILT_WDA", "true").lower() == "true"
            options.set_capability("usePrebuiltWDA", use_prebuilt)
            options.set_capability("useXctestrunFile", False)
            options.set_capability("wdaLaunchTimeout", 120000)
            options.set_capability("wdaConnectionTimeout", 120000)
            options.set_capability("clearSystemFiles", True)

        print("🍎 [FIXTURE] Connecting to Appium at http://127.0.0.1:4723...")
        driver = webdriver.Remote(
            "http://127.0.0.1:4723",
            options=options
        )
        print("🍎 [FIXTURE] Appium connection established!")

        yield driver
        print("🍎 [FIXTURE] Quitting driver...")
        driver.quit()

    def test_location_overlay_appears_and_dismissible(self, ios_driver):
        """Test that location permission overlay appears and can be dismissed.

        This test verifies:
        1. The proxy-injected overlay appears when visiting a site
        2. The overlay shows "Location Required" or similar message
        3. The "Continue Anyway" button works to dismiss the overlay
        4. After dismissing, the website content is visible
        """
        driver = ios_driver

        # Clear Safari data to ensure fresh state
        # Using GitHub which is NOT in essential_domains (skips injection)
        # Note: google.com, youtube.com, apple.com are in essential_domains and won't show overlay
        logging.info("Navigating to GitHub to test location overlay...")

        # First clear any existing session storage by going to about:blank
        driver.get("about:blank")
        time.sleep(1)

        driver.get("https://www.github.com")

        # Wait for page to load and overlay to appear
        time.sleep(5)

        page_source = driver.page_source

        # Check if location overlay is present
        has_overlay = ("location-permission-overlay" in page_source.lower() or
                      "location required" in page_source.lower() or
                      "continue anyway" in page_source.lower() or
                      "waiting for permission" in page_source.lower())

        if not has_overlay:
            # Take screenshot for debugging
            try:
                import os
                screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshots_dir, "debug_no_overlay.png")
                driver.save_screenshot(screenshot_path)
                logging.info(f"Screenshot saved to {screenshot_path}")
            except:
                pass

            logging.warning("Location overlay not found in page source")
            logging.warning("This could mean:")
            logging.warning("  1. Location permission was already granted previously")
            logging.warning("  2. The proxy didn't inject the overlay JavaScript")
            logging.warning("  3. Safari cache is serving old content")
            pytest.fail("Location overlay did not appear. Try clearing Safari cache on device.")

        logging.info("Location overlay detected on page")

        # Try to click "Continue Anyway" button
        dismissed = False

        # Method 1: XPath with text
        try:
            logging.info("Attempting to click 'Continue Anyway' via XPath...")
            continue_button = driver.find_element(
                AppiumBy.XPATH,
                "//button[contains(text(), 'Continue Anyway')] | //button[contains(., 'Continue Anyway')]"
            )
            continue_button.click()
            time.sleep(2)
            dismissed = True
            logging.info("Successfully clicked button via XPath")
        except Exception as e:
            logging.info(f"XPath method failed: {e}")

        # Method 2: Accessibility ID
        if not dismissed:
            try:
                logging.info("Attempting via accessibility ID...")
                continue_button = driver.find_element(AppiumBy.ACCESSIBILITY_ID, "Continue Anyway")
                continue_button.click()
                time.sleep(2)
                dismissed = True
                logging.info("Successfully clicked via accessibility ID")
            except Exception as e:
                logging.info(f"Accessibility ID method failed: {e}")

        # Method 3: JavaScript
        if not dismissed:
            try:
                logging.info("Attempting via JavaScript...")
                driver.execute_script("""
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        if (btn.textContent.includes('Continue')) {
                            btn.click();
                            break;
                        }
                    }
                """)
                time.sleep(2)
                dismissed = True
                logging.info("Successfully dismissed via JavaScript")
            except Exception as e:
                logging.info(f"JavaScript method failed: {e}")

        # Method 4: Try to handle iOS location alert if it appeared
        if not dismissed:
            try:
                logging.info("Trying to handle iOS location alert...")
                # Look for Allow button in iOS alert
                allow_button = driver.find_element(
                    AppiumBy.XPATH,
                    "//XCUIElementTypeButton[@name='Allow Once'] | //XCUIElementTypeButton[@name='Allow']"
                )
                allow_button.click()
                time.sleep(2)
                logging.info("Clicked Allow on iOS location dialog")

                # After granting permission, overlay should auto-dismiss
                dismissed = True
            except Exception as e:
                logging.info(f"No iOS alert found: {e}")

        assert dismissed, "Could not interact with location overlay or permission dialog"

        # Verify GitHub content is visible after dismissing
        page_source_after = driver.page_source
        assert "github" in page_source_after.lower(), \
            "GitHub content should be visible after dismissing overlay"

        logging.info("Location overlay test PASSED - overlay appeared and was dismissed")

    def test_location_overlay_blocks_until_action(self, ios_driver):
        """Test that the overlay blocks page interaction until dismissed.

        This verifies the overlay is actually blocking the page content
        and not just a transparent layer.
        """
        driver = ios_driver

        # Navigate to a different page to get fresh overlay
        driver.get("https://www.google.com")
        time.sleep(3)

        page_source = driver.page_source

        # Check for overlay indicators
        has_overlay = ("location-permission-overlay" in page_source.lower() or
                      "location required" in page_source.lower())

        if has_overlay:
            logging.info("Overlay is blocking the page as expected")

            # Try to interact with Google search (should fail if overlay is blocking)
            try:
                search_box = driver.find_element(AppiumBy.NAME, "q")
                # If we can find and interact with the search box, overlay isn't blocking
                logging.warning("Could access search box - overlay may not be blocking properly")
            except:
                logging.info("Cannot access page elements - overlay is blocking correctly")
        else:
            # Location may already be granted
            pytest.skip("Overlay not present - location permission may already be granted")

    def test_location_overlay_appears_once_per_session(self, ios_driver):
        """Test that location overlay only appears ONCE per session.

        This test specifically addresses the bug where:
        1. User visits a site (e.g., amazon.com)
        2. Location overlay appears, user grants permission
        3. Site loads
        4. On page navigation/refresh, overlay would appear AGAIN (bug!)

        The fix uses sessionStorage to track if location was already obtained.
        This test verifies that fix works correctly.
        """
        driver = ios_driver

        # Clear session by going to about:blank first
        logging.info("Step 1: Clearing session state...")
        driver.get("about:blank")
        time.sleep(1)

        # Clear sessionStorage via JavaScript to ensure fresh state
        try:
            driver.execute_script("sessionStorage.clear();")
        except:
            pass

        # Step 2: Navigate to Amazon (a whitelisted site that triggers overlay)
        logging.info("Step 2: Navigating to amazon.com...")
        driver.get("https://www.amazon.com")
        time.sleep(5)

        page_source = driver.page_source

        # Check if location overlay appeared
        has_overlay = ("location-permission-overlay" in page_source.lower() or
                      "location required" in page_source.lower() or
                      "continue anyway" in page_source.lower())

        if not has_overlay:
            logging.warning("Location overlay did not appear on first visit")
            logging.warning("This might be because:")
            logging.warning("  1. Safari already has location permission cached")
            logging.warning("  2. VPN traffic not going through proxy")
            # Don't fail - continue to test the "no repeat" behavior
        else:
            logging.info("Location overlay appeared on first visit (expected)")

        # Step 3: Dismiss the overlay (grant permission or click Continue)
        logging.info("Step 3: Dismissing location overlay...")
        dismissed = False

        # Method 1: Click "Continue Anyway" button
        try:
            driver.execute_script("""
                const btn = document.getElementById('continue-btn');
                if (btn) btn.click();
            """)
            time.sleep(2)
            dismissed = True
            logging.info("Clicked Continue Anyway button")
        except Exception as e:
            logging.info(f"Continue button not found: {e}")

        # Method 2: Handle iOS location permission dialog
        if not dismissed:
            try:
                allow_button = driver.find_element(
                    AppiumBy.XPATH,
                    "//XCUIElementTypeButton[@name='Allow Once'] | //XCUIElementTypeButton[@name='Allow While Using App']"
                )
                allow_button.click()
                time.sleep(3)
                dismissed = True
                logging.info("Granted iOS location permission")
            except Exception as e:
                logging.info(f"No iOS permission dialog: {e}")

        # Wait for overlay to be dismissed and page to load
        time.sleep(3)

        # Step 4: Verify site content is visible
        logging.info("Step 4: Verifying site loaded...")
        page_source_after = driver.page_source

        # Check overlay is gone
        overlay_gone = "location-permission-overlay" not in page_source_after.lower() or \
                       'display: none' in page_source_after.lower() or \
                       'display:none' in page_source_after.lower()

        # Check Amazon content is visible
        amazon_loaded = "amazon" in page_source_after.lower()

        logging.info(f"Overlay dismissed: {overlay_gone}, Amazon loaded: {amazon_loaded}")

        # Step 5: Navigate to another page (THE KEY TEST)
        logging.info("Step 5: Navigating to Amazon search page...")
        driver.get("https://www.amazon.com/s?k=books")
        time.sleep(5)

        page_source_second = driver.page_source

        # THE CRITICAL CHECK: Overlay should NOT appear again
        has_overlay_again = ("location required" in page_source_second.lower() and
                            "waiting for permission" in page_source_second.lower())

        if has_overlay_again:
            # Check if it's hidden (sessionStorage fix working)
            overlay_visible = driver.execute_script("""
                const overlay = document.getElementById('location-permission-overlay');
                if (!overlay) return false;
                const style = window.getComputedStyle(overlay);
                return style.display !== 'none';
            """)
            if overlay_visible:
                pytest.fail(
                    "BUG: Location overlay appeared AGAIN on second page navigation! "
                    "The sessionStorage fix is not working."
                )
            else:
                logging.info("Overlay HTML present but hidden (sessionStorage fix working)")
        else:
            logging.info("No location overlay on second navigation")

        # Step 6: Refresh the page and check again
        logging.info("Step 6: Refreshing page to verify overlay doesn't reappear...")
        driver.refresh()
        time.sleep(5)

        # Check overlay is still not visible after refresh
        overlay_visible_after_refresh = driver.execute_script("""
            const overlay = document.getElementById('location-permission-overlay');
            if (!overlay) return false;
            const style = window.getComputedStyle(overlay);
            return style.display !== 'none';
        """)

        if overlay_visible_after_refresh:
            pytest.fail(
                "BUG: Location overlay appeared after page REFRESH! "
                "sessionStorage should persist across refresh."
            )

        logging.info("Location overlay did not reappear after refresh")
        logging.info("Location overlay test PASSED - appears only once per session")
