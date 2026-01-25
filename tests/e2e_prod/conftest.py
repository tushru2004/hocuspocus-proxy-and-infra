"""Pytest configuration for production E2E verification tests.

These tests run against the PRODUCTION database - no switching, no seeding.
Used for quick VPN verification after startup.
"""
import pytest
import subprocess
import os

from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.appium_connection import AppiumConnection
from selenium.webdriver.remote.client_config import ClientConfig

K8S_NAMESPACE = "hocuspocus"


def _run_kubectl_command(args: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a kubectl command."""
    cmd = ["kubectl", "-n", K8S_NAMESPACE] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="session", autouse=True)
def appium_preflight_check():
    """Verify Appium server is running."""
    print("\n" + "="*60)
    print("🚀 [PROD] Running production verification preflight...")
    print("="*60)

    try:
        import urllib.request
        urllib.request.urlopen('http://127.0.0.1:4723/status', timeout=5)
        print("✅ Appium server is running")
    except Exception as e:
        pytest.exit(f"Appium server not running! Start with: appium\nError: {e}")

    yield

    print("\n🏁 [PROD] Verification completed")


@pytest.fixture(scope="session")
def ios_driver():
    """Create iOS Appium driver for production verification."""
    print("\n🔌 [PROD] Creating Appium driver...")

    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.browser_name = "Safari"
    options.automation_name = "XCUITest"
    options.no_reset = False  # Allow reset to clear Safari data
    options.set_capability("autoAcceptAlerts", True)
    # Clear Safari cache/cookies on session start
    options.set_capability("safari:safariClearWebsiteData", True)

    # Real device config
    options.platform_version = "18.7.3"
    options.device_name = "Tushar's iPhone"
    options.udid = "00008020-0004695621DA002E"
    options.set_capability("xcodeOrgId", "QG9U628JFD")
    options.set_capability("xcodeSigningId", "Apple Development")
    options.updated_wda_bundle_id = "com.hocuspocus.WebDriverAgentRunner"
    options.set_capability("usePrebuiltWDA", True)
    options.set_capability("derivedDataPath", "/Users/tushar/Library/Developer/Xcode/DerivedData/WebDriverAgent-clkfczzppyhxsqbbzslmbrysyvbk")
    options.set_capability("skipUninstall", True)
    options.set_capability("showXcodeLog", True)
    options.set_capability("wdaLaunchTimeout", 600000)  # 10 minutes
    options.set_capability("wdaConnectionTimeout", 240000)  # 4 minutes
    options.set_capability("newCommandTimeout", 300)  # 5 minutes

    client_config = ClientConfig(
        remote_server_addr="http://127.0.0.1:4723",
        timeout=600  # 10 minutes for HTTP requests
    )
    appium_connection = AppiumConnection(client_config=client_config)

    driver = webdriver.Remote(
        command_executor=appium_connection,
        options=options
    )
    print("✅ [PROD] Connected to device")

    yield driver

    print("🔌 [PROD] Closing driver...")
    driver.quit()


@pytest.fixture(scope="session")
def mitmproxy_logs():
    """Fixture to get mitmproxy logs."""
    def get_logs(tail: int = 50) -> str:
        result = _run_kubectl_command([
            "logs", "deployment/mitmproxy", f"--tail={tail}"
        ])
        return result.stdout
    return get_logs
