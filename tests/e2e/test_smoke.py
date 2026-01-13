"""
Simple smoke test to verify E2E test setup is working.

Run this test first to verify:
1. Appium server is running
2. iOS device is connected
3. WebDriverAgent can connect
4. Safari can be automated

Usage:
    pytest tests/e2e/test_smoke.py -v -s
"""
import pytest
import os
from appium import webdriver
from appium.options.ios import XCUITestOptions


class TestSmoke:
    """Quick smoke test to verify test infrastructure."""

    @pytest.fixture(scope="class")
    def driver(self):
        """Set up iOS driver with minimal config."""
        print("\n🔌 [SMOKE] Creating Appium driver...")

        device_type = os.getenv('IOS_DEVICE_TYPE', 'real').lower()

        options = XCUITestOptions()
        options.platform_name = "iOS"
        options.browser_name = "Safari"
        options.automation_name = "XCUITest"
        options.no_reset = True
        options.set_capability("autoAcceptAlerts", True)

        if device_type == 'simulator':
            options.platform_version = "26.2"
            options.device_name = "iPhone 17 Pro"
            options.set_capability("wdaLaunchTimeout", 60000)
        else:
            # Real device config
            options.platform_version = "18.7.3"
            options.device_name = "Tushar's iPhone"
            options.udid = "00008020-0004695621DA002E"
            options.set_capability("xcodeOrgId", "QG9U628JFD")
            options.set_capability("xcodeSigningId", "iPhone Developer")
            options.updated_wda_bundle_id = "com.hocuspocus.WebDriverAgentRunner"
            options.set_capability("usePrebuiltWDA", True)
            options.set_capability("wdaLaunchTimeout", 600000)  # 10 minutes - real devices can be slow
            options.set_capability("wdaConnectionTimeout", 240000)  # 4 minutes

        print("🔌 [SMOKE] Connecting to Appium at http://127.0.0.1:4723...")

        # Set longer timeout for session creation (WDA can take a while)
        options.set_capability("newCommandTimeout", 300)  # 5 min command timeout

        # Configure HTTP client with longer timeout for session creation
        from appium.webdriver.appium_connection import AppiumConnection
        from selenium.webdriver.remote.client_config import ClientConfig

        client_config = ClientConfig(
            remote_server_addr="http://127.0.0.1:4723",
            timeout=600  # 10 minutes for HTTP requests (real devices can be slow)
        )
        appium_connection = AppiumConnection(client_config=client_config)

        driver = webdriver.Remote(
            command_executor=appium_connection,
            options=options
        )
        print("✅ [SMOKE] Appium connection successful!")

        yield driver

        print("🔌 [SMOKE] Closing driver...")
        driver.quit()

    @pytest.mark.timeout(600)
    def test_can_connect_to_device(self, driver):
        """Test that we can connect to the iOS device."""
        print("\n📱 [SMOKE] Testing device connection...")

        # Just verify we have a session
        assert driver.session_id is not None, "Should have a valid session"
        print(f"✅ [SMOKE] Session ID: {driver.session_id}")

    @pytest.mark.timeout(30)
    def test_can_navigate_to_url(self, driver):
        """Test that Safari can navigate to a URL."""
        print("\n🌐 [SMOKE] Testing URL navigation...")

        driver.get("https://example.com")

        # Verify page loaded
        assert "example" in driver.page_source.lower(), "Should load example.com"
        print("✅ [SMOKE] Successfully navigated to example.com")

    @pytest.mark.timeout(10)
    def test_can_get_page_source(self, driver):
        """Test that we can read page source."""
        print("\n📄 [SMOKE] Testing page source access...")

        source = driver.page_source
        assert len(source) > 0, "Should get page source"
        print(f"✅ [SMOKE] Got page source ({len(source)} chars)")
