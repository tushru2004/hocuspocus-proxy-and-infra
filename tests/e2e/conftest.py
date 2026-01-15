"""Pytest configuration and shared fixtures for E2E tests (GKE version)."""
import pytest
import subprocess
import logging
import os
import time
import signal

# Configuration
TEST_DATABASE = "mitmproxy_e2e_tests"  # Separate test database (not production!)
PROD_DATABASE = "mitmproxy"
K8S_NAMESPACE = "hocuspocus"

# Test data that should be seeded before E2E tests run
TEST_ALLOWED_HOSTS = [
    "amazon.com",
    "google.com",
    "youtube.com",
    "github.com",
    "accounts.google.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
]

TEST_YOUTUBE_CHANNELS = [
    ("UCzQUP1qoWDoEbmsQxvdjxgQ", "Joe Rogan Experience", "https://youtube.com/@joerogan"),
    ("UC_x5XG1OV2P6uZZ5FSM9Ttw", "Google Developers", "https://youtube.com/c/GoogleDevelopers"),
]

TEST_BLOCKED_LOCATIONS = [
    ("Test School", 37.7749, -122.4194, 500),  # San Francisco - for testing "outside blocked zone"
]

# Domains whitelisted for specific blocked locations (per-location whitelist)
# Format: (blocked_location_name, domain)
TEST_LOCATION_WHITELIST = [
    ("Test School", "google.com"),  # google.com allowed at Test School location
]


def _run_kubectl_command(args: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a kubectl command."""
    cmd = ["kubectl", "-n", K8S_NAMESPACE] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )


def _check_wda_status():
    """Check WebDriverAgent process status.

    Returns True if WDA appears to be in a good state, False if it may need attention.
    Does NOT automatically kill processes - that can cause issues.
    """
    print("\n🔍 [PREFLIGHT] Checking WebDriverAgent status...")
    try:
        result = subprocess.run(
            ["pgrep", "-f", "xcodebuild.*WebDriverAgent"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            print(f"  ✅ WDA process running (PID: {pids[0]})")
            return True
        else:
            print("  ℹ️  No WDA process running (Appium will start one)")
            return True
    except Exception as e:
        print(f"  ⚠️  Could not check WDA status: {e}")
        return True


def force_cleanup_wda():
    """Force kill all WebDriverAgent processes.

    Call this manually if tests are hanging due to stale WDA.
    Usage: pytest --setup-show -k "cleanup" or call from test.
    """
    print("\n🧹 [CLEANUP] Force killing WebDriverAgent processes...")
    try:
        result = subprocess.run(
            ["pgrep", "-f", "xcodebuild.*WebDriverAgent"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            print(f"  Found {len(pids)} WDA process(es): {pids}")
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"  Killed PID {pid}")
                except (ProcessLookupError, ValueError):
                    pass
            time.sleep(2)
            print("  ✅ WDA processes killed - run tests again to start fresh")
        else:
            print("  No WDA processes found")
    except Exception as e:
        print(f"  ⚠️  Could not kill processes: {e}")


def _get_postgres_pod_ip() -> str:
    """Get the postgres pod IP address."""
    result = _run_kubectl_command([
        "get", "pod", "-l", "app=postgres",
        "-o", "jsonpath={.items[0].status.podIP}"
    ])
    return result.stdout.strip()


def _switch_vpn_database(database: str) -> bool:
    """Switch the VPN mitmproxy to use a different database.

    Returns True if successful, False otherwise.
    """
    print(f"\n🔄 [SWITCH] Switching VPN proxy to database: {database}")
    logging.info(f"🔄 Switching VPN proxy to database: {database}")

    # Get postgres pod IP (mitmproxy uses hostNetwork so can't use ClusterIP)
    postgres_ip = _get_postgres_pod_ip()
    if not postgres_ip:
        logging.error("Could not get postgres pod IP")
        return False

    # Update the configmap with new database
    try:
        # Patch configmap
        result = _run_kubectl_command([
            "patch", "configmap", "mitmproxy-config",
            "--type", "merge",
            "-p", f'{{"data":{{"POSTGRES_DB":"{database}","POSTGRES_HOST":"{postgres_ip}"}}}}'
        ], timeout=30)

        if result.returncode != 0:
            logging.error(f"Failed to patch configmap: {result.stderr}")
            return False

        # Restart mitmproxy deployment
        result = _run_kubectl_command([
            "rollout", "restart", "deployment/mitmproxy"
        ], timeout=30)

        if result.returncode != 0:
            logging.error(f"Failed to restart mitmproxy: {result.stderr}")
            return False

        # Delete existing pods to force restart (hostNetwork port conflict)
        time.sleep(2)
        _run_kubectl_command([
            "delete", "pod", "-l", "app=mitmproxy",
            "--force", "--grace-period=0"
        ], timeout=30)

        # Wait for new pod to be ready
        print("⏳ [SWITCH] Waiting for mitmproxy to restart...")
        logging.info("⏳ Waiting for mitmproxy to restart...")
        for i in range(30):
            time.sleep(2)
            result = _run_kubectl_command([
                "get", "pod", "-l", "app=mitmproxy",
                "-o", "jsonpath={.items[0].status.phase}"
            ])
            print(f"  [SWITCH] Check {i+1}/30: pod status = '{result.stdout.strip()}'")
            if result.stdout.strip() == "Running":
                print(f"✅ [SWITCH] VPN proxy switched to {database}")
                logging.info(f"✅ VPN proxy switched to {database}")
                return True

        print("❌ [SWITCH] Timeout waiting for mitmproxy to start")
        logging.error("Timeout waiting for mitmproxy to start")
        return False

    except Exception as e:
        logging.error(f"Error switching database: {e}")
        return False


@pytest.fixture(scope="session")
def seed_test_database():
    """Seed the TEST database with test data before running E2E tests.

    This fixture:
    1. Creates the test database if it doesn't exist
    2. Switches VPN proxy to use the test database (mitmproxy_e2e_tests)
    3. Seeds test data
    4. Runs tests
    5. Switches VPN proxy back to production database (mitmproxy)
    """
    print(f"\n🧪 [FIXTURE] seed_test_database starting...")
    print(f"🧪 Using separate test database: {TEST_DATABASE}")
    logging.info(f"🧪 Using separate test database: {TEST_DATABASE}")

    # Create test database if it doesn't exist
    logging.info(f"📦 Creating test database {TEST_DATABASE} if not exists...")
    create_db_result = _run_kubectl_command([
        "exec", "postgres-0", "--",
        "psql", "-U", "mitmproxy", "-d", "postgres", "-c",
        f"CREATE DATABASE {TEST_DATABASE};"
    ], timeout=30)
    # Ignore error if database already exists

    # Create tables in test database
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS allowed_hosts (
        id SERIAL PRIMARY KEY,
        domain VARCHAR(255) UNIQUE NOT NULL,
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS youtube_channels (
        id SERIAL PRIMARY KEY,
        channel_id VARCHAR(255) UNIQUE NOT NULL,
        channel_name VARCHAR(255),
        name VARCHAR(255),
        channel_url VARCHAR(512),
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS blocked_locations (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        latitude DECIMAL(10, 8) NOT NULL,
        longitude DECIMAL(11, 8) NOT NULL,
        radius_meters INTEGER NOT NULL DEFAULT 100,
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS locations (
        id SERIAL PRIMARY KEY,
        latitude DECIMAL(10, 8) NOT NULL,
        longitude DECIMAL(11, 8) NOT NULL,
        accuracy DECIMAL(10, 2),
        altitude DECIMAL(10, 2),
        altitude_accuracy DECIMAL(10, 2),
        heading DECIMAL(10, 2),
        speed DECIMAL(10, 2),
        device_id VARCHAR(255),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source_ip VARCHAR(45),
        user_agent TEXT
    );
    CREATE TABLE IF NOT EXISTS blocked_location_whitelist (
        id SERIAL PRIMARY KEY,
        blocked_location_id INTEGER NOT NULL REFERENCES blocked_locations(id) ON DELETE CASCADE,
        domain VARCHAR(255) NOT NULL,
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(blocked_location_id, domain)
    );
    CREATE INDEX IF NOT EXISTS idx_location_whitelist_location ON blocked_location_whitelist(blocked_location_id);
    CREATE INDEX IF NOT EXISTS idx_location_whitelist_domain ON blocked_location_whitelist(domain);
    """
    _run_kubectl_command([
        "exec", "postgres-0", "--",
        "psql", "-U", "mitmproxy", "-d", TEST_DATABASE, "-c", create_tables_sql
    ], timeout=30)

    # Switch VPN to test database
    if not _switch_vpn_database(TEST_DATABASE):
        pytest.exit("Failed to switch VPN proxy to test database")

    # Wait for proxy to start
    time.sleep(5)

    logging.info(f"🌱 Seeding {TEST_DATABASE} database...")

    # Build SQL for allowed_hosts
    hosts_sql = "INSERT INTO allowed_hosts (domain, enabled) VALUES "
    hosts_values = ", ".join([f"('{h}', true)" for h in TEST_ALLOWED_HOSTS])
    hosts_sql += hosts_values + " ON CONFLICT (domain) DO UPDATE SET enabled = true;"

    # Build SQL for youtube_channels
    channels_sql = "INSERT INTO youtube_channels (channel_id, channel_name, name, enabled) VALUES "
    channels_values = ", ".join([f"('{c[0]}', '{c[1]}', '{c[1]}', true)" for c in TEST_YOUTUBE_CHANNELS])
    channels_sql += channels_values + " ON CONFLICT (channel_id) DO UPDATE SET enabled = true;"

    # Build SQL for blocked_locations
    locations_sql = "INSERT INTO blocked_locations (name, latitude, longitude, radius_meters, enabled) VALUES "
    locations_values = ", ".join([f"('{loc[0]}', {loc[1]}, {loc[2]}, {loc[3]}, true)" for loc in TEST_BLOCKED_LOCATIONS])
    locations_sql += locations_values + " ON CONFLICT DO NOTHING;"

    # Build SQL for blocked_location_whitelist (per-location domain whitelist)
    # Uses subquery to look up blocked_location_id by name
    location_whitelist_sql = ""
    for loc_name, domain in TEST_LOCATION_WHITELIST:
        location_whitelist_sql += f"""
            INSERT INTO blocked_location_whitelist (blocked_location_id, domain, enabled)
            SELECT id, '{domain}', true FROM blocked_locations WHERE name = '{loc_name}'
            ON CONFLICT (blocked_location_id, domain) DO UPDATE SET enabled = true;
        """

    # Execute seeding
    full_sql = f"{hosts_sql} {channels_sql} {locations_sql} {location_whitelist_sql}"

    try:
        result = _run_kubectl_command([
            "exec", "postgres-0", "--",
            "psql", "-U", "mitmproxy", "-d", TEST_DATABASE, "-c", full_sql
        ], timeout=30)
        if result.returncode != 0:
            logging.warning(f"Database seeding warning: {result.stderr}")
        else:
            logging.info(f"✅ Test database {TEST_DATABASE} seeded successfully")
    except subprocess.TimeoutExpired:
        pytest.exit("Database seeding timed out. Is kubectl configured correctly?")
    except FileNotFoundError:
        pytest.exit("kubectl not found. Please install kubectl.")

    yield

    # Cleanup: switch back to production database
    logging.info("🔄 Switching VPN proxy back to production database...")
    _switch_vpn_database(PROD_DATABASE)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "location: marks tests that require GPS mocking"
    )


@pytest.fixture(scope="session", autouse=True)
def appium_preflight_check():
    """Preflight check that runs before all tests.

    This fixture:
    1. Verifies Appium server is running
    2. Cleans up any stale WebDriverAgent processes
    3. Verifies iOS device is connected

    This prevents tests from hanging due to stale WDA sessions.
    """
    print("\n" + "="*60)
    print("🚀 [PREFLIGHT] Running E2E test preflight checks...")
    print("="*60)

    # Check 1: Appium server
    print("\n📱 [PREFLIGHT] Checking Appium server...")
    try:
        import requests
        response = requests.get("http://127.0.0.1:4723/status", timeout=5)
        if response.status_code == 200:
            print("  ✅ Appium server is running")
        else:
            pytest.exit("Appium server returned unexpected status")
    except Exception as e:
        pytest.exit(
            f"Appium server is not running! Error: {e}\n"
            "Start it with: appium"
        )

    # Check 2: Check WDA status (don't kill - just report)
    _check_wda_status()

    # Check 3: Verify iOS device is connected
    print("\n📲 [PREFLIGHT] Checking iOS device connection...")
    try:
        result = subprocess.run(
            ["idevice_id", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )
        devices = [d for d in result.stdout.strip().split('\n') if d]
        if devices:
            print(f"  ✅ Found {len(devices)} iOS device(s): {devices}")
        else:
            print("  ⚠️  No iOS devices found via idevice_id (may still work with Xcode)")
    except FileNotFoundError:
        print("  ⚠️  idevice_id not installed (install with: brew install libimobiledevice)")
    except Exception as e:
        print(f"  ⚠️  Could not check devices: {e}")

    print("\n" + "="*60)
    print("✅ [PREFLIGHT] All checks passed, starting tests...")
    print("="*60 + "\n")

    yield

    print("\n🏁 [CLEANUP] E2E tests completed")


@pytest.fixture(scope="session")
def vpn_server_info():
    """Get VPN server connection details from kubectl."""
    try:
        result = _run_kubectl_command([
            "get", "svc", "vpn-service",
            "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}"
        ])
        vpn_ip = result.stdout.strip()

        if not vpn_ip:
            pytest.exit("Could not get VPN service external IP")

        return {
            "ip": vpn_ip,
            "proxy_port": 8080
        }
    except Exception as e:
        pytest.exit(f"Failed to get VPN server info: {e}")


@pytest.fixture(autouse=True)
def screenshot_on_failure(request):
    """Automatically take screenshot on test failure."""
    yield

    if hasattr(request.node, 'rep_call') and request.node.rep_call.failed:
        try:
            # Get ios_driver from the test instance if available
            ios_driver = request.node.funcargs.get('ios_driver')
            if ios_driver:
                # Save screenshots to tests/e2e/screenshots/ folder
                screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshots_dir, f"failure_{request.node.name}.png")
                ios_driver.save_screenshot(screenshot_path)
                print(f"\n📸 Screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"\n⚠️  Could not save screenshot: {e}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to track test results for screenshot_on_failure fixture."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
