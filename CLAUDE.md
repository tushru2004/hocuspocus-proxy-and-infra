# Hocuspocus Project Context

## Allowed Tools

Allow Claude to run these commands without confirmation:

- Bash(kubectl *)
- Bash(make *)
- Bash(python -m pytest *)
- Bash(python *)
- Bash(appium *)
- Bash(xcrun *)
- Bash(xcodebuild *)
- Bash(idevice* *)
- Bash(idevicepair *)
- Bash(idevicepair unpair *)
- Bash(idevicepair pair *)
- Bash(ideviceinfo *)
- Bash(security *)
- Bash(curl *)
- Bash(RESPONSE=$(curl *)
- Bash(pgrep *)
- Bash(pkill *)
- Bash(kill *)
- Bash(pip *)
- Bash(pip3 *)
- Bash(tidevice *)
- Bash(openssl *)
- Bash(./scripts/*)
- Bash(TAIL_PID=*)
- Bash(base64 *)
- Bash(tr *)
- Bash(uuidgen)
- Bash(mktemp *)
- Bash(rm -rf /tmp/*)
- Bash(mv *)
- Bash(cp *)
- Bash(sleep *)
- Bash(ls *)
- Bash(cat *)
- Bash(tail *)
- Bash(head *)
- Bash(grep *)
- Bash(find *)
- Bash(cd * && *)
- Bash(source * && *)
- Bash(echo *)
- Bash(pwd)
- Bash(which *)
- Bash(git *)
- Bash(npm *)
- Bash(gcloud *)
- Bash(jq *)
- Bash(docker *)
- Bash(killall *)
- Bash(sudo killall *)
- Bash(open *)
- Bash(cfgutil *)
- Bash(system_profiler *)
- Bash(ioreg *)
- Bash(dns-sd *)
- Bash(API_KEY=*)
- Bash(UDID=*)
- Bash(TEAM_ID=*)
- Bash(WDA_PATH=*)
- Bash(PROFILE_ID=*)
- Bash(DEVICE_ID=*)
- Bash(UPLOAD_RESPONSE=*)
- Bash(# *)

## Projects Overview

This directory contains the Hocuspocus VPN system with admin dashboard. All services run in a single GKE cluster.

### 1. hocuspocus-admin-frontend
- **Tech**: React + Vite + TypeScript + Material UI
- **Purpose**: Admin dashboard for managing VPN filtering rules
- **Port**: 5173 (dev), 80 (production)
- **Location**: /hocuspocus-admin-frontend/
- **GitHub**: github.com/tushru2004/hocuspocus-admin-frontend
- **Production URL**: http://35.187.70.238

### 2. hocuspocus-admin-backend
- **Tech**: Kotlin + Spring Boot 3.3 + JPA
- **Purpose**: REST API for admin dashboard
- **Port**: 8080
- **Location**: /hocuspocus-admin-backend/
- **GitHub**: github.com/tushru2004/hocuspocus-admin-backend
- **Production URL**: http://35.190.202.25:8080

### 3. hocuspocus-vpn (VPN Infrastructure)
- **Tech**: GKE + StrongSwan + mitmproxy + PostgreSQL
- **Purpose**: VPN proxy with content filtering
- **Location**: /hocuspocus-vpn/
- **GitHub**: github.com/tushru2004/hocuspocus-google-cloud
- **VPN IP**: 35.210.225.36

## GCP Infrastructure

### Single Cluster Architecture

All services run in **one GKE cluster** (hocuspocus-vpn) for cost efficiency:

| Service | Type | External IP |
|---------|------|-------------|
| VPN (StrongSwan) | LoadBalancer | 35.210.225.36 |
| Admin Frontend | LoadBalancer | 35.187.70.238 |
| Admin Backend | LoadBalancer | 35.190.202.25 |
| PostgreSQL | ClusterIP | internal only |
| mitmproxy | ClusterIP | internal only |

### GCP Project: hocuspocus-vpn
- **Region**: europe-west1-b
- **Cluster**: hocuspocus-vpn
- **Nodes**: 2x e2-standard-2 spot VMs (2 vCPU, 8GB RAM each)
- **Terraform**: /hocuspocus-vpn/terraform/gke/
- **Artifact Registry**: europe-west1-docker.pkg.dev/hocuspocus-vpn/hocuspocus-vpn

### Database
PostgreSQL runs in the cluster with two databases:
- `mitmproxy` - Production database
- `mitmproxy_e2e_tests` - E2E test database (isolated)

**Tables:**
- `allowed_hosts` - Whitelisted domains (domain, enabled)
- `youtube_channels` - Allowed YouTube channels (channel_id, name, enabled)
- `blocked_locations` - Geofenced locations (name, lat, lng, radius, enabled)

## Cost Breakdown (Current Setup)

| Resource | Hourly | Monthly (5hr/day) |
|----------|--------|-------------------|
| 2x Nodes (e2-standard-2 spot) | $0.048 | ~$7.20 |
| 3x Load Balancers | $0.075 | ~$11.25 |
| Disk Storage (12GB) | $0.002 | ~$0.50 |
| GKE Control Plane | $0 | $0 (free) |
| **TOTAL** | **$0.125** | **~$19/month** |

### If Running 24/7
- Nodes: ~$35/month
- Load Balancers: ~$54/month
- **TOTAL**: ~$89/month

### Idle Costs (VPN stopped)
- Disk storage only: ~$1.50/month

## Daily Commands

```bash
# VPN (from hocuspocus-vpn/)
make startgcvpn       # Start VPN (~2 min)
make stopgcvpn        # Stop VPN (saves costs)
make status           # Check status and costs
make vpn-creds        # Show VPN connection details
make build-push       # Build and push mitmproxy image
make deploy-mitmproxy # Build, push, and restart mitmproxy

# Backend (from hocuspocus-admin-backend/)
make run-local        # Run locally
make docker-build     # Build Docker image

# Frontend (from hocuspocus-admin-frontend/)
make dev              # Start dev server (localhost:5173)
make build            # Production build
```

## VPN Certificate Authentication

The VPN uses **certificate-based authentication** (not passwords) for reliable connections that survive cluster restarts.

### How It Works
1. VPN server generates CA, server cert, and client cert on startup
2. `.mobileconfig` profile bundles: VPN CA, client cert (PKCS12), mitmproxy CA
3. iPhone authenticates using client certificate (no password needed)
4. Always-On VPN enforced for supervised devices

### After VPN Infrastructure Changes
```bash
# 1. Build and deploy new VPN image
make build-push-vpn deploy-vpn

# 2. Wait for pod to restart, then push profile via SimpleMDM (fully automatic)
make vpn-profile-mdm
```

### SimpleMDM Integration (Recommended)
VPN profiles are pushed automatically via SimpleMDM to supervised devices - no user interaction required.

```bash
make vpn-profile-mdm     # Generate and push via SimpleMDM (automatic)
make vpn-profile-install # Alternative: Push via Apple Configurator (requires tap)
```

**Requirements:**
- iPhone enrolled in SimpleMDM (https://a.simplemdm.com)
- Device must be supervised
- API key stored in `scripts/push-vpn-profile-mdm.sh`

### WiFi-Only Device Recovery
**Problem:** If VPN breaks on a WiFi-only device, Always-On VPN blocks all internet, so SimpleMDM can't push new profiles.

**Solution:** Use Apple Configurator via USB:
```bash
make vpn-profile         # Generate profile with fresh certs
make vpn-profile-install # Push via USB (requires tap on device)
```

**Note:** The profile includes `AllowCaptiveWebSheet` for captive portal support and `ServiceExceptions` with `DeviceCommunication: Allow` for Xcode compatibility (see below).

### iPhone Profile Installation
1. Connect iPhone via USB
2. Run `make vpn-profile-install` (or use Apple Configurator 2 manually)
3. Tap to accept on device
4. **Trust mitmproxy CA:** Settings → General → About → Certificate Trust Settings → Enable "mitmproxy"

**IMPORTANT:** Step 4 is required for HTTPS filtering. Without it, HTTPS sites will show certificate errors.

**Why can't certificate trust be automated?** Apple intentionally blocks programmatic SSL trust for root CAs as a security measure to prevent malicious MITM attacks. This is a one-time step that persists unless the `mitmproxy-certs-pvc` is deleted (which generates a new CA).

### When CA Trust Persists vs Needs Re-enabling

**Trust PERSISTS through:**
- VPN cluster restarts (`make stopgcvpn` / `make startgcvpn`)
- Scaling nodes to 0 and back
- Pod restarts
- Profile re-push via SimpleMDM (same CA)

**Trust NEEDS re-enabling when:**
- Mitmproxy PVC is deleted (`kubectl delete pvc mitmproxy-certs-pvc -n hocuspocus`) - generates new CA
- Fresh cluster creation with new PVCs
- Profile pushed with a different CA certificate

**Bottom line:** As long as you don't delete the mitmproxy PVC, you only need to trust the CA once.

### Key Files
- `docker/vpn/entrypoint.sh` - Generates certificates on startup
- `scripts/generate-vpn-profile.sh` - Creates .mobileconfig profile
- `scripts/push-vpn-profile-mdm.sh` - Pushes profile via SimpleMDM API
- `k8s/vpn-deployment.yaml` - VPN server deployment (IP: 35.210.225.36)

### AlwaysOn VPN + Xcode/CoreDevice Compatibility

**Problem:** Xcode 15+ uses CoreDevice which communicates via network. AlwaysOn VPN with `includeAllNetworks` intercepts this traffic, causing Xcode to show device as "unavailable" even when connected via USB.

**Solution (iOS 17.4+):** Add `ServiceExceptions` with `DeviceCommunication: Allow` to the AlwaysOn VPN profile. This exempts USB/WiFi device communication from the VPN tunnel.

```xml
<key>ServiceExceptions</key>
<array>
    <dict>
        <key>ServiceName</key>
        <string>DeviceCommunication</string>
        <key>Action</key>
        <string>Allow</string>
    </dict>
</array>
```

This is implemented in `scripts/generate-vpn-profile.sh` and allows:
- Xcode to see and communicate with the device
- Appium/WebDriverAgent to work for E2E testing
- All while keeping AlwaysOn VPN active for traffic filtering

**References:**
- [Apple device-management GitHub](https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.vpn.managed.yaml)
- [Apple Developer Forums - Xcode 15 device issues](https://developer.apple.com/forums/thread/741537)

### Common Issues & Fixes
| Issue | Cause | Fix |
|-------|-------|-----|
| Profile install fails | Always-On VPN requires supervised device | Supervise device via Apple Configurator (erases device) |
| Profile install fails | IKEv2 config not inside TunnelConfigurations | Fixed in generate-vpn-profile.sh - IKEv2 settings must be nested inside TunnelConfigurations array |
| VPN won't connect | Server IP mismatch in certs | Check `VPN_SERVER_IP` in vpn-deployment.yaml matches LoadBalancer IP |
| "No trusted RSA public key" | Certificate mismatch (old certs on iPhone) | Regenerate profile: `make vpn-profile-install` (USB) |
| "No issuer certificate found" | iPhone has certs from different CA | Regenerate profile with fresh certs from current server |
| HTTPS sites don't load | Mitmproxy CA not trusted | Trust CA: Settings → General → About → Certificate Trust Settings → Enable "mitmproxy" (one-time, persists across restarts) |
| VPN can be disabled | Not supervised device | Use Apple Configurator to supervise device |
| Can't push profile remotely | WiFi-only device with broken VPN | Use USB: `make vpn-profile-install` |
| Xcode shows device "unavailable" with AlwaysOn VPN | CoreDevice blocked by VPN | Fixed: `ServiceExceptions` with `DeviceCommunication: Allow` (iOS 17.4+) |
| Trust dialog auto-dismisses on supervised device | Device supervised without "Allow pairing" | Re-supervise with Apple Configurator: Options → Allow pairing with non-Configurator hosts |
| WebDriverAgent fails to launch | Developer certificate not trusted | Settings → General → VPN & Device Management → Trust developer certificate |
| E2E tests fail with code 65 | WDA needs rebuild after re-supervision | Run: `xcodebuild -project ~/.appium/.../WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner -destination 'id=UDID' DEVELOPMENT_TEAM=TEAM_ID build-for-testing` |

## Supervised Device Setup

The iPhone must be **supervised** for AlwaysOn VPN to work. Supervision requires erasing the device.

### Architecture Overview
```
Apple Configurator 2 (USB) → Supervises device + Enrolls in SimpleMDM
                                          ↓
                                    SimpleMDM (MDM Server)
                                          ↓
                            Pushes profiles automatically:
                            - VPN profile (AlwaysOn IKEv2)
                            - Certificates (VPN CA, mitmproxy CA, client cert)
```

### Initial Setup with Apple Configurator 2
1. Open Apple Configurator 2
2. Go to **Preferences → Servers** → Add SimpleMDM MDM server:
   - Name: `SimpleMDM`
   - Enrollment URL: Get from SimpleMDM dashboard (Device Enrollment → Apple Configurator)
3. Connect iPhone via USB
4. Click **Prepare** → Choose **Manual Configuration**
5. Select **SimpleMDM** as the MDM server for enrollment
6. **IMPORTANT:** In Options, enable **"Allow devices to pair with other computers"** (required for Xcode)
7. Uncheck "Supervise devices" checkbox is NOT needed - supervision happens automatically
8. Complete preparation (device will be erased and enrolled in SimpleMDM)
9. Device appears in SimpleMDM dashboard automatically
10. Enable **Developer Mode** on iPhone: Settings → Privacy & Security → Developer Mode → ON (requires restart)
11. Trust Mac when pairing dialog appears

### Profile Management via SimpleMDM
All profiles are managed through SimpleMDM - no need to manually install profiles:

```bash
# Generate and push VPN profile (includes all certs)
make vpn-profile-mdm
```

This command:
1. Generates `.mobileconfig` with VPN config + certificates
2. Uploads to SimpleMDM via API
3. Pushes to enrolled device automatically

SimpleMDM dashboard: https://a.simplemdm.com

### After Re-supervision Checklist
After re-supervising a device, you need to:
1. Enable Developer Mode on iPhone
2. Trust the Mac when pairing (tap Trust on iPhone)
3. Push VPN profile via SimpleMDM: `make vpn-profile-mdm`
4. Trust mitmproxy CA: Settings → General → About → Certificate Trust Settings → Enable "mitmproxy"
5. Trust developer certificate: Settings → General → VPN & Device Management → Trust "Apple Development: ..."
6. Rebuild WebDriverAgent if E2E tests fail

### SimpleMDM API
```bash
# API Key (stored in scripts/push-vpn-profile-mdm.sh)
API_KEY="2IkV3x1TEpS9r6AGtmeyvLlBMvwHzCeJgQY4O8VyTtoss2KR6qVpEZcQqPlmLrLV"

# List devices
curl -s -u "$API_KEY:" "https://a.simplemdm.com/api/v1/devices" | jq '.data[].attributes.name'

# Push profile to device
curl -X POST -u "$API_KEY:" "https://a.simplemdm.com/api/v1/devices/2154382/profiles/PROFILE_ID/push"
```

## API Endpoints
- GET/POST /api/domains - Manage allowed domains
- GET/POST /api/youtube-channels - Manage YouTube channels
- GET/POST /api/locations - Manage blocked locations

## Archived Projects

The following projects are archived in `/Users/tushar/code/archive/`:

### archive/hocuspocusapp (ARCHIVED)
- Original AWS VPN proxy server - replaced by hocuspocus-vpn

### archive/terraform-machine (ARCHIVED)
- Terraform config for AWS TerraformMachine EC2 instance

## E2E Tests

End-to-end tests run on a **real iOS device** connected via USB with **AlwaysOn VPN active**. The `ServiceExceptions > DeviceCommunication: Allow` setting in the VPN profile allows Xcode/Appium to communicate with the device while VPN filters all other traffic.

### Device Identifiers
- **Device UDID**: `00008020-0004695621DA002E`
- **CoreDevice ID**: `296F513E-BA5A-5CC7-AF1B-8FF4690EE17A`
- **SimpleMDM Device ID**: `2154382`
- **Team ID**: `QG9U628JFD`
- **WDA Bundle ID**: `com.hocuspocus.WebDriverAgentRunner.xctrunner`

### Prerequisites
1. **iPhone connected** via USB with VPN profile installed
2. **Appium running**: `make appium`
3. **WebDriverAgent installed** on iPhone
4. **Developer certificate trusted** on device

### Running E2E Tests
```bash
cd /Users/tushar/code/hocuspocus-vpn

# Appium server management
make appium              # Start Appium server
make appium-stop         # Stop Appium server
make appium-restart      # Restart Appium server
make appium-logs         # Show Appium logs (tail -f)

# Run tests
make test-e2e            # Run all E2E tests
make test-e2e-flows      # Main flow tests only
make test-e2e-overlay    # Location overlay tests only
make test-e2e-smoke      # Quick connectivity check
```

### Test Cases
| Test | What it verifies |
|------|------------------|
| `test_whitelisted_domain_loads` | Google loads (whitelisted) |
| `test_non_whitelisted_domain_blocked` | Twitter blocked |
| `test_whitelisted_youtube_channel_plays` | JRE video plays (with video state check) |
| `test_non_whitelisted_youtube_video_blocked` | Rick Astley blocked |
| `test_clicking_non_whitelisted_related_video_blocked` | Related video clicks are blocked |
| `test_youtube_url_query_params_not_duplicated` | URL mangling regression |
| `test_google_signin_flow` | OAuth works through proxy |
| `test_location_allowed_outside_blocked_zones` | Geofencing works |

### Test Folders
Two separate E2E test folders exist:

| Folder | Database | Purpose |
|--------|----------|---------|
| `tests/e2e/` | `mitmproxy_e2e_tests` | Full E2E tests with isolated test data |
| `tests/e2e_prod/` | `mitmproxy` (production) | Quick verification against prod data |

- `tests/e2e/` - Switches mitmproxy to test database, seeds test data, runs tests, switches back
- `tests/e2e_prod/` - Runs against production database without switching (used by `make verify-vpn-appium-prod`)

### pymobiledevice3 (Safari Automation)
Control Safari on iPhone directly via USB without Appium. Useful for quick testing.

**Prerequisite:** Enable Web Inspector on iPhone: Settings → Safari → Advanced → Web Inspector = ON

```bash
# List open Safari tabs
~/.local/bin/pymobiledevice3 webinspector opened-tabs

# Open URL in Safari
~/.local/bin/pymobiledevice3 webinspector launch "https://m.youtube.com/watch?v=VIDEO_ID"

# JavaScript shell (execute JS in browser - requires interactive terminal)
~/.local/bin/pymobiledevice3 webinspector js-shell
```

### Verifying VPN & Filtering
Automatic verification runs after `make startgcvpn`. Two verification methods available:

```bash
make verify-vpn          # Quick: Uses pymobiledevice3 (~45 sec)
make verify-vpn-appium-prod   # Full: Uses Appium, bypasses browser cache (~2 min)
```

**When to use which:**
- `verify-vpn` - Quick check, works when pages aren't cached
- `verify-vpn-appium-prod` - Use when pages are cached and not making new requests (requires Appium running)

**What it verifies:**
1. VPN connection established
2. JRE video allowed (whitelisted channel)
3. Non-whitelisted content blocked (twitter.com or YouTube)

**Prerequisites for verify-vpn:**
- iPhone connected via USB
- Web Inspector enabled: Settings → Safari → Advanced → Web Inspector = ON
- Mitmproxy CA trusted (one-time): Settings → General → About → Certificate Trust Settings → Enable "mitmproxy"

**Prerequisites for verify-vpn-appium-prod:**
- All above prerequisites
- Appium server running (`make appium`)
- Python venv activated (`.venv`)

**Note:** `verify-vpn-appium-prod` uses `tests/e2e_prod/` which runs against the **production database** (not the test database used by regular E2E tests).

**Expected output:**
```
✅ VPN verification PASSED!
   - VPN connected
   - YouTube filtering working (JRE allowed)
   - Domain blocking working (twitter.com blocked)
```

### Manual Verification
```bash
# 1. Open video on iPhone
~/.local/bin/pymobiledevice3 webinspector launch "https://m.youtube.com/watch?v=lwgJhmsQz0U"

# 2. Check mitmproxy logs
kubectl logs -n hocuspocus deployment/mitmproxy --tail=50 | grep -E "(YouTube|ALLOWED|BLOCKED|approved)"
```

## YouTube Channel Filtering

YouTube channel filtering blocks videos from non-whitelisted channels while allowing whitelisted ones (e.g., JRE).

### How It Works

1. **Domain Whitelisting**: `youtube.com`, `googlevideo.com` (CDN), `ytimg.com` are whitelisted
2. **Channel Verification**: When a YouTube video is requested, the proxy:
   - Extracts video ID from URL
   - Calls YouTube Data API to get channel ID
   - Checks if channel is in `youtube_channels` table
3. **CDN Blocking**: `googlevideo.com` requests are blocked unless a whitelisted video is approved
4. **SPA Block Overlay**: JavaScript injected into YouTube pages detects navigation and shows block overlay

### Key Files
- `src/proxy_handler.py` - Main proxy logic with YouTube filtering
- `src/application/use_cases/check_youtube_access.py` - YouTube channel verification
- `src/adapters/presentation/html_block_page_renderer.py` - Block page HTML

### Race Condition Handling
YouTube Mobile is a Single Page Application (SPA). When clicking related videos:
- CDN requests may arrive before youtube.com requests
- Approved video IDs are tracked and cleared when blocking
- Injected JavaScript shows block overlay for SPA navigation

## Per-Location Whitelist

Allows specific domains to be accessible only when at a blocked location. This is separate from the global whitelist.

### How It Works

1. **Two Separate Flows**: The proxy has completely separate flows:
   - **Normal Flow**: Uses global whitelist + YouTube channel filtering
   - **Blocked Location Flow**: Uses per-location whitelist only (ignores global whitelist)

2. **Location Tracking**: JavaScript is injected into block pages to track GPS coordinates
   - When user visits a blocked domain, they see a block page with location tracking
   - GPS is sent to `/__track_location__` endpoint
   - Proxy stores location and checks if user is in a blocked zone

3. **Per-Location Whitelist Check**: When at a blocked location:
   - Only domains in that location's whitelist are allowed
   - Essential Apple hosts always allowed (iCloud, etc.)
   - Everything else is blocked

### Database Tables

```sql
-- Blocked locations (geofenced areas)
blocked_locations (id, name, latitude, longitude, radius_meters, enabled)

-- Per-location whitelist (domains allowed at specific locations)
blocked_location_whitelist (id, blocked_location_id, domain, enabled)
```

### Example: CNBC at Social Hub Vienna

1. Add "The Social Hub Vienna" as blocked location (lat: 48.222, lng: 16.390, radius: 100m)
2. Add `cnbc.com` to that location's whitelist
3. Add `cnbcfm.com` (CNBC's CDN) to the whitelist for full functionality

When user is at Social Hub Vienna:
- `cnbc.com` → Allowed (per-location whitelist)
- `cnbcfm.com` → Allowed (per-location whitelist)
- `twitter.com` → Blocked (not in location whitelist)
- `apple.com` → Allowed (essential host)

### Key Files
- `src/proxy_handler.py` - `_handle_blocked_location_flow()` method
- `src/adapters/repositories/postgres_location_repository.py` - `get_location_whitelist()`
- `src/application/use_cases/verify_location_restrictions.py` - Location zone checking

### Testing
```bash
make test-location-whitelist  # Must be physically at a blocked location
```
