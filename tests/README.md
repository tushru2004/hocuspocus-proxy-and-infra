# End-to-End Tests

These E2E tests run on a **real iOS device** connected to the VPN proxy to verify the full system works correctly.

## Quick Start

```bash
# 1. Start Appium server (in separate terminal)
appium

# 2. Run all E2E tests (using Makefile)
make test-e2e

# Or run directly with pytest:
PYTHONPATH=src pytest tests/e2e/ -v
```

## Prerequisites

### 1. Hardware Requirements
- Mac with Xcode installed
- Real iPhone connected via USB with:
  - IKEv2 VPN profile installed and connected
  - Developer mode enabled
  - Trusted developer certificate

### 2. Software Requirements

```bash
# Install Appium globally
npm install -g appium

# Install XCUITest driver for iOS
appium driver install xcuitest

# Install Python dependencies
pip install appium-python-client pytest
```

### 3. VPN Server Running

Ensure the AWS VPN server is running:

```bash
cd terraform/vpn
terraform output vpn_server_public_ip
```

The tests will fail with a timeout error if the VPN server is not reachable.

### 4. WebDriverAgent Setup (One-time, Critical!)

WebDriverAgent (WDA) must be built and installed on your iPhone. **This is the most common source of test failures.**

#### Step-by-step Setup:

1. **Open WebDriverAgent in Xcode:**
   ```bash
   open ~/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent/WebDriverAgent.xcodeproj
   ```

2. **Select the WebDriverAgentRunner target** (not IntegrationApp)

3. **Configure Signing:**
   - Go to **Signing & Capabilities** tab
   - Select your Team (personal or organization)
   - Set a unique Bundle Identifier (e.g., `com.yourname.WebDriverAgentRunner`)

   > **Important:** Free Apple Developer accounts have a limit of 10 App IDs per 7 days. If you hit this limit, reuse an existing Bundle ID.

4. **Select your iPhone as the target device:**
   - Click the device dropdown next to the scheme selector
   - Choose your connected iPhone

5. **Build and run WebDriverAgent:**
   - Press **Cmd+U** (Product → Test)
   - This builds WDA and installs it on your iPhone

6. **Trust the developer certificate on iPhone:**
   - Go to Settings → General → VPN & Device Management
   - Find your developer certificate and tap "Trust"

## Test Configuration

Tests are configured for a specific device. Update these values in `test_ios_flows.py` if using a different device:

```python
options.platform_version = "18.7.3"
options.device_name = "Tushar's iPhone"
options.udid = "00008020-0004695621DA002E"
options.updated_wda_bundle_id = "com.hocuspocus.WebDriverAgentRunner"
```

To find your device info:
```bash
# List connected devices
xcrun xctrace list devices

# Get UDID
idevice_id -l
```

## Test Cases

| Test | Description | What it Verifies |
|------|-------------|------------------|
| `test_whitelisted_domain_loads` | Navigate to Google | Whitelisted domains load correctly |
| `test_non_whitelisted_domain_blocked` | Navigate to Twitter | Non-whitelisted domains are blocked |
| `test_whitelisted_youtube_channel_plays` | Play JRE video | Whitelisted YouTube channels work |
| `test_non_whitelisted_youtube_video_blocked` | Play non-whitelisted video | Non-whitelisted YouTube videos blocked |
| `test_youtube_url_query_params_not_duplicated` | Video URL with params | Regression: URL query params not duplicated |
| `test_google_signin_flow` | Access Google sign-in | OAuth flows work through proxy |
| `test_location_overlay_appears_and_dismissible` | Check location overlay | Proxy-injected overlay appears |
| `test_location_allowed_outside_blocked_zones` | Browse outside blocked zone | Location check allows browsing |

## Database Seeding

Tests automatically seed the database with test data via `conftest.py`. The seed data includes:

**Allowed Hosts:**
- google.com, youtube.com, github.com, amazon.com
- accounts.google.com, googleapis.com, gstatic.com, googleusercontent.com

**YouTube Channels:**
- UC_x5XG1OV2P6uZZ5FSM9Ttw (Google Developers)
- UCzQUP1qoWDoEbmsQxvdjxgQ (Joe Rogan Experience)

**Blocked Locations:**
- Test School (San Francisco) - for testing location blocking

## Troubleshooting

### Error: "xcodebuild failed with code 65"

**Cause:** WebDriverAgent is not properly signed or installed on the device.

**Solution:**
1. Open WebDriverAgent.xcodeproj in Xcode
2. Select **WebDriverAgentRunner** target
3. Go to Signing & Capabilities
4. Select your Team and set Bundle Identifier
5. Select your iPhone as target device
6. Press Cmd+U to build and install
7. Set `usePrebuiltWDA: True` in test config (already configured)

### Error: "Maximum App ID limit reached"

**Cause:** Free Apple Developer accounts can only create 10 App IDs per 7 days.

**Solution:**
1. Check existing App IDs in WebDriverAgent project:
   ```bash
   grep -r "PRODUCT_BUNDLE_IDENTIFIER" ~/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent/*.xcodeproj/project.pbxproj
   ```
2. Reuse an existing Bundle ID instead of creating a new one
3. Or wait 7 days for the limit to reset

### Error: "VPN server not responding" / Timeout

**Cause:** The AWS EC2 instance running the VPN server is stopped or unreachable.

**Solution:**
1. Start the EC2 instance:
   ```bash
   cd terraform/vpn
   terraform apply
   ```
2. Verify the server is running:
   ```bash
   terraform output vpn_server_public_ip
   # Try to reach it
   curl -s --connect-timeout 5 http://$(terraform output -raw vpn_server_public_ip):22 || echo "Server reachable"
   ```

### Error: "Port #8100 is occupied"

**Cause:** A previous WebDriverAgent session is still running.

**Solution:**
```bash
# Kill Appium and restart
pkill -f appium
sleep 2
appium
```

### Error: "Unable to launch WebDriverAgent"

**Cause:** WDA needs to be rebuilt or the device needs to trust the certificate.

**Solution:**
1. On iPhone: Settings → General → VPN & Device Management → Trust your developer certificate
2. In Xcode: Clean build folder (Cmd+Shift+K) and rebuild WDA (Cmd+U)
3. Ensure `usePrebuiltWDA: True` is set in test config

### Tests pass on simulator but fail on real device

**Cause:** Simulator tests don't go through the VPN proxy.

**Explanation:**
- iOS Simulator cannot connect to IKEv2 VPN
- Only real devices with VPN connected will test actual proxy functionality
- Simulator tests will show "positive" results (sites load) but won't test blocking

### Blocking tests fail (sites load instead of being blocked)

**Cause:** VPN is not connected on the iPhone.

**Solution:**
1. Check iPhone Settings → VPN → Ensure VPN is connected
2. Clear Safari cache: Settings → Safari → Clear History and Website Data
3. Check proxy logs: `make logs`

## Common Issues We Encountered

### 1. WebDriverAgent Build Failures

The most common issue was WebDriverAgent failing to build with "xcodebuild failed with code 65". This was resolved by:

1. Opening WebDriverAgent.xcodeproj directly in Xcode
2. Manually configuring signing for WebDriverAgentRunner target
3. Building and running on the device from Xcode first (Cmd+U)
4. Setting `usePrebuiltWDA: True` in the test configuration

### 2. App ID Limit

We hit the 10 App ID limit on free Apple Developer accounts. The WebDriverAgent project creates multiple bundle IDs:
- com.hocuspocus.WebDriverAgentLib
- com.hocuspocus.WebDriverAgentRunner
- com.hocuspocus.IntegrationApp
- etc.

**Fix:** Reuse existing bundle IDs instead of creating new ones.

### 3. VPN Server Not Running

Tests would timeout trying to connect to the VPN server IP. The fixture checks VPN server reachability before running tests.

**Fix:** Ensure EC2 instance is running with `terraform apply`.

### 4. Simulator vs Real Device Confusion

Tests behave differently on simulator vs real device:
- **Simulator:** No VPN connection → no proxy → no blocking → tests pass incorrectly
- **Real device:** VPN connected → proxy active → blocking works → tests accurate

**Fix:** Always run E2E tests on real device with VPN connected.

### 5. Port 8100 Stuck

After test failures, WebDriverAgent sometimes leaves port 8100 occupied.

**Fix:** Kill and restart Appium: `pkill -f appium && appium`

## Running Tests

### Using Makefile (Recommended)
```bash
# Run all E2E tests
make test-e2e

# Run main flow tests only (with autoAcceptAlerts)
make test-e2e-flows

# Run location overlay tests only (without autoAcceptAlerts)
make test-e2e-overlay

# Run simulator tests (currently skipped)
make test-simulator
```

### Using pytest directly
```bash
# Full test suite
PYTHONPATH=src pytest tests/e2e/ -v

# Single test
PYTHONPATH=src pytest tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_whitelisted_domain_loads -v

# With debug output
PYTHONPATH=src pytest tests/e2e/ -v -s
```

## Test Files

| File | Tests | autoAcceptAlerts | Purpose |
|------|-------|------------------|---------|
| `test_ios_flows.py` | 6 | Yes | Main proxy flow tests |
| `test_location_overlay.py` | 2 | No | Location overlay appearance tests |

### Expected Results

```
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_whitelisted_domain_loads PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_non_whitelisted_domain_blocked PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_jre_video_plays PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_non_jre_youtube_video_blocked PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_google_signin_flow PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_location_overlay_appears_and_dismissible PASSED
tests/e2e/test_ios_flows.py::TestIOSProxyFlows::test_location_allowed_outside_blocked_zones PASSED

======================== 7 passed in ~60s =========================
```
