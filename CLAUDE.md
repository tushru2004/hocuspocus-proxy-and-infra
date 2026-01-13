# Hocuspocus Project Context

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
- **Nodes**: 2x e2-small spot VMs
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
| 2x Nodes (e2-small spot) | $0.012 | ~$1.80 |
| 3x Load Balancers | $0.075 | ~$11.25 |
| Disk Storage (12GB) | $0.002 | ~$0.50 |
| GKE Control Plane | $0 | $0 (free) |
| **TOTAL** | **$0.089** | **~$13-14/month** |

### If Running 24/7
- Nodes: ~$9/month
- Load Balancers: ~$54/month
- **TOTAL**: ~$63/month

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

**VPN Credentials**:
- Server: 35.210.225.36
- Type: IKEv2
- Username: vpnuser
- Password: (run `make vpn-creds` to see)

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

End-to-end tests run on a **real iOS device** connected via USB.

### Prerequisites
1. **iPhone connected** via USB with VPN profile installed
2. **Appium running**: `appium`
3. **WebDriverAgent installed** on iPhone

### Running E2E Tests
```bash
cd /Users/tushar/code/hocuspocus-vpn
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

### Test Database
E2E tests use `mitmproxy_e2e_tests` database to avoid polluting production.

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
