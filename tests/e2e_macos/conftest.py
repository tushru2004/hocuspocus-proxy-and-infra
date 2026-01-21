"""Pytest configuration for macOS E2E verification tests.

These tests run against the PRODUCTION database - no switching, no seeding.
Used for quick VPN verification on MacBook Air.
"""
import pytest
import subprocess
import os

from selenium import webdriver
from selenium.webdriver.safari.options import Options as SafariOptions

K8S_NAMESPACE = "hocuspocus"


def _run_kubectl_command(args: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a kubectl command."""
    # Use full path to kubectl and set PATH for gke-gcloud-auth-plugin
    import os
    home = os.path.expanduser("~")
    kubectl_path = os.path.join(home, "bin", "kubectl")

    # Check if ~/bin/kubectl exists, otherwise use system kubectl
    if not os.path.exists(kubectl_path):
        kubectl_path = "kubectl"

    env = os.environ.copy()
    env["PATH"] = f"{home}/bin:{home}/google-cloud-sdk/bin:" + env.get("PATH", "")

    cmd = [kubectl_path, "-n", K8S_NAMESPACE] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


@pytest.fixture(scope="session", autouse=True)
def safari_preflight_check():
    """Verify Safari WebDriver is available."""
    print("\n" + "="*60)
    print("🚀 [PROD macOS] Running production verification preflight...")
    print("="*60)

    # Check if safaridriver is available
    try:
        result = subprocess.run(
            ["safaridriver", "--version"],
            capture_output=True, text=True, timeout=5
        )
        print(f"✅ Safari WebDriver available: {result.stdout.strip()}")
    except Exception as e:
        pytest.exit(f"Safari WebDriver not available!\nEnable it: safaridriver --enable\nError: {e}")

    yield

    print("\n🏁 [PROD macOS] Verification completed")


@pytest.fixture(scope="session")
def macos_driver():
    """Create Safari WebDriver for macOS verification."""
    print("\n🔌 [PROD macOS] Creating Safari WebDriver...")

    options = SafariOptions()

    # Create Safari driver (uses safaridriver on macOS)
    driver = webdriver.Safari(options=options)
    driver.implicitly_wait(10)

    print("✅ [PROD macOS] Safari WebDriver connected")

    yield driver

    print("🔌 [PROD macOS] Closing driver...")
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
