"""
Mitmproxy addon for traffic filtering, location tracking, and content blocking.

Refactored using Clean Architecture principles.

Handles:
- Domain whitelisting/blocking
- YouTube channel filtering
- GPS location tracking and location-based blocking
- Custom block pages

Run as follows: mitmproxy -s proxy_handler.py
"""
import re
import logging
import json
import ipaddress
from typing import Optional
from urllib.parse import urlencode

from mitmproxy import ctx, http
import tldextract

from infrastructure.config import AppConfig
from infrastructure.dependency_container import DependencyContainer
from domain.value_objects import GPSCoordinates, LocationData, BlockReason
from application.use_cases import (
    CheckDomainAccess,
    CheckYouTubeAccess,
    StoreLocation,
    VerifyLocationRestrictions
)
from adapters.presentation import HTMLBlockPageRenderer


class ProxyHandler:
    """Main mitmproxy addon using Clean Architecture."""

    def __init__(self):
        self.num = 0

        # Load configuration
        self.config = AppConfig.load()

        # Initialize dependency container
        self.container = DependencyContainer(self.config)

        # Get use cases
        self.check_domain_access = self.container.get_check_domain_access_use_case()
        self.check_youtube_access = self.container.get_check_youtube_access_use_case()
        self.store_location_use_case = self.container.get_store_location_use_case()
        self.verify_location = self.container.get_verify_location_restrictions_use_case()

        # Get repositories (for per-location whitelist)
        self.location_repository = self.container.get_location_repository()

        # Get services
        self.block_page_renderer = self.container.get_block_page_renderer()

        # Captive portal tracking
        self.redirect_tracker = {}

        # Track recently approved YouTube video IDs for googlevideo.com correlation
        self._approved_video_ids: set[str] = set()

    def request(self, flow):
        """Handle incoming requests."""
        self.num += 1
        logging.info(f"We've seen {self.num} flows")
        logging.info(f"Request URL: {flow.request.host}")

        # Handle location tracking endpoint
        if flow.request.path == "/__track_location__" and flow.request.method == "POST":
            self._handle_location_tracking(flow)
            return

        # Handle YouTube video check endpoint (for SPA blocking overlay)
        if flow.request.path.startswith("/__check_youtube_video__"):
            self._handle_youtube_video_check(flow)
            return

        full_host = flow.request.host

        # ================================================================
        # TWO SEPARATE FLOWS based on location:
        # 1. BLOCKED LOCATION FLOW - Uses per-location whitelist only
        # 2. NORMAL FLOW - Uses global whitelist + YouTube channel filtering
        # ================================================================

        if self.verify_location.is_blocked:
            # BLOCKED LOCATION FLOW
            self._handle_blocked_location_flow(flow, full_host)
            return

        # NORMAL FLOW (not at blocked location)
        # Extract full hostname and base domain
        full_hostname, base_domain = self._extract_base_domain(flow)

        # Check domain access (pass both full hostname and base domain)
        decision = self.check_domain_access.execute(full_hostname, base_domain)

        if decision.allowed:
            # Special handling for YouTube
            if self.check_youtube_access.is_enabled and 'youtube.com' in full_hostname:
                youtube_url = self._build_full_url(flow)
                logging.info(f"🔍 Checking YouTube URL: {youtube_url}")

                # Extract video ID early to detect video switches
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(youtube_url)
                query = parse_qs(parsed.query)
                current_video_id = query.get('v', query.get('docid', [None]))[0]

                # If we see a NEW video ID, clear old approvals BEFORE checking
                # This prevents race conditions where googlevideo loads before blocking
                if current_video_id and current_video_id not in self._approved_video_ids:
                    if self._approved_video_ids:
                        logging.info(f"🔄 New video {current_video_id} detected, clearing old approvals: {self._approved_video_ids}")
                        self._approved_video_ids.clear()

                youtube_decision = self.check_youtube_access.execute(youtube_url)

                if not youtube_decision.allowed:
                    logging.info("🚫 BLOCKING YouTube video (channel not whitelisted)")
                    # Clear approved videos when blocking - user switched to non-whitelisted content
                    self._approved_video_ids.clear()
                    logging.info("🗑️ Cleared approved video IDs")
                    block_page = self.block_page_renderer.render_youtube_block_page()
                    block_page = self._inject_location_script_into_html(block_page)
                    flow.response = http.Response.make(
                        403,
                        block_page.encode('utf-8'),
                        {"Content-Type": "text/html; charset=utf-8"}
                    )
                    return
                else:
                    # Track approved video ID for googlevideo.com correlation
                    if "whitelisted" in youtube_decision.message and current_video_id:
                        self._approved_video_ids.add(current_video_id)
                        logging.info(f"📝 Tracking approved video ID: {current_video_id}")
                    logging.info(f"✅ YouTube check passed: {youtube_url}")

            # Special handling for googlevideo.com (YouTube CDN)
            if self.check_youtube_access.is_enabled and 'googlevideo.com' in full_hostname:
                referer = flow.request.headers.get("Referer", "")
                logging.info(f"🔍 Checking googlevideo.com request (Referer: {referer})")

                if referer and 'youtube.com' in referer:
                    # Try to extract video ID from referer and check channel
                    youtube_decision = self.check_youtube_access.execute(referer)

                    if "Not a YouTube video URL" in youtube_decision.message:
                        # Couldn't extract video ID from referer
                        # Allow if we have approved videos (set when youtube.com/watch was allowed)
                        if self._approved_video_ids:
                            logging.info(f"✅ googlevideo.com allowed ({len(self._approved_video_ids)} approved videos)")
                        else:
                            logging.info("🚫 BLOCKING googlevideo.com (no approved videos)")
                            block_page = self.block_page_renderer.render_youtube_block_page()
                            block_page = self._inject_location_script_into_html(block_page)
                            flow.response = http.Response.make(
                                403,
                                block_page.encode('utf-8'),
                                {"Content-Type": "text/html; charset=utf-8"}
                            )
                            return
                    elif not youtube_decision.allowed:
                        logging.info("🚫 BLOCKING googlevideo.com (YouTube channel not whitelisted)")
                        block_page = self.block_page_renderer.render_youtube_block_page()
                        block_page = self._inject_location_script_into_html(block_page)
                        flow.response = http.Response.make(
                            403,
                            block_page.encode('utf-8'),
                            {"Content-Type": "text/html; charset=utf-8"}
                        )
                        return
                    else:
                        logging.info(f"✅ googlevideo.com allowed (channel whitelisted via Referer)")
                else:
                    # No referer or not from youtube - block by default when filtering is enabled
                    logging.info("🚫 BLOCKING googlevideo.com (no YouTube Referer to verify channel)")
                    block_page = self.block_page_renderer.render_youtube_block_page()
                    block_page = self._inject_location_script_into_html(block_page)
                    flow.response = http.Response.make(
                        403,
                        block_page.encode('utf-8'),
                        {"Content-Type": "text/html; charset=utf-8"}
                    )
                    return

            logging.info(f"✅ Allowing: {full_hostname} (host: {full_host})")
        else:
            # Block
            logging.info(f"🚫 BLOCKING: {base_domain} - {decision.message}")
            block_page = self.block_page_renderer.render_domain_block_page(base_domain)
            # Inject location tracking script so we can detect if at blocked location
            block_page = self._inject_location_script_into_html(block_page)
            flow.response = http.Response.make(
                403,
                block_page.encode('utf-8'),
                {"Content-Type": "text/html; charset=utf-8"}
            )
            return

    def response(self, flow):
        """Handle responses - inject location tracking and detect captive portals."""
        if not flow.response:
            return

        # Inject location tracking JavaScript into HTML responses
        self._inject_location_tracking_script(flow)

        # Inject YouTube video blocking script for SPA navigation
        self._inject_youtube_blocking_script(flow)

        # Detect captive portals
        self._detect_captive_portal(flow)

    def load(self, loader):
        """Load configuration on startup."""
        loader.add_option(
            name="block_global",
            typespec=bool,
            default=False,
            help="Disable block global option",
        )

    def _handle_location_tracking(self, flow):
        """Handle location tracking endpoint."""
        logging.info(f"📍 Received location tracking request from {flow.request.host}")
        try:
            data = json.loads(flow.request.content)

            # Parse location data
            coordinates = GPSCoordinates(
                latitude=data.get('latitude'),
                longitude=data.get('longitude')
            )

            location_data = LocationData(
                coordinates=coordinates,
                accuracy=data.get('accuracy'),
                altitude=data.get('altitude'),
                url=data.get('url', 'unknown'),
                timestamp=data.get('timestamp'),
                device_id=data.get('device_id', 'iPhone')
            )

            # Store location
            self.store_location_use_case.execute(location_data)

            # Verify location restrictions
            location_decision = self.verify_location.execute(coordinates)

            # Build response
            response_data = {
                "status": "ok",
                "blocked": not location_decision.allowed
            }

            # If blocked, include block page
            if not location_decision.allowed:
                blocked_zone_name = self.verify_location.blocked_zone_name or "a blocked location"
                response_data["block_page"] = self.block_page_renderer.render_location_block_page(
                    blocked_zone_name
                )

            flow.response = http.Response.make(
                200,
                json.dumps(response_data).encode('utf-8'),
                {"Content-Type": "application/json"}
            )
        except Exception as e:
            logging.error(f"❌ Error processing location: {e}")
            flow.response = http.Response.make(
                400,
                b'{"status": "error"}',
                {"Content-Type": "application/json"}
            )

    def _handle_youtube_video_check(self, flow):
        """Handle YouTube video check endpoint for SPA blocking overlay."""
        try:
            from urllib.parse import urlparse, parse_qs

            # Extract video ID from query string
            parsed = urlparse(flow.request.path)
            query = parse_qs(parsed.query)
            video_id = query.get('v', [None])[0]

            if not video_id:
                flow.response = http.Response.make(
                    200,
                    json.dumps({"blocked": False, "reason": "no video ID"}).encode('utf-8'),
                    {"Content-Type": "application/json"}
                )
                return

            # Check if YouTube filtering is enabled
            if not self.check_youtube_access.is_enabled:
                flow.response = http.Response.make(
                    200,
                    json.dumps({"blocked": False, "reason": "filtering disabled"}).encode('utf-8'),
                    {"Content-Type": "application/json"}
                )
                return

            # Check video access using the YouTube use case
            fake_url = f"https://www.youtube.com/watch?v={video_id}"
            decision = self.check_youtube_access.execute(fake_url)

            blocked = not decision.allowed
            logging.info(f"📺 YouTube video check: {video_id} -> {'BLOCKED' if blocked else 'ALLOWED'}")

            # Update approved video tracking
            if decision.allowed and "whitelisted" in decision.message:
                self._approved_video_ids.add(video_id)
            elif blocked:
                self._approved_video_ids.discard(video_id)

            flow.response = http.Response.make(
                200,
                json.dumps({
                    "blocked": blocked,
                    "video_id": video_id,
                    "reason": decision.message
                }).encode('utf-8'),
                {"Content-Type": "application/json"}
            )

        except Exception as e:
            logging.error(f"❌ Error checking YouTube video: {e}")
            flow.response = http.Response.make(
                200,
                json.dumps({"blocked": False, "error": str(e)}).encode('utf-8'),
                {"Content-Type": "application/json"}
            )

    def _handle_blocked_location_flow(self, flow, full_host: str) -> None:
        """Handle requests when user is at a blocked location.

        At blocked locations, we use a COMPLETELY DIFFERENT FLOW:
        - Only check per-location whitelist (NOT global whitelist)
        - Allow essential Apple hosts
        - Block everything else

        This is separate from the normal flow which uses global whitelist
        and YouTube channel filtering.
        """
        blocked_zone_name = self.verify_location.blocked_zone_name or "a blocked location"
        blocked_zone_id = self.verify_location.blocked_zone_id

        # Extract hostname and base domain (handles IP addresses and SNI)
        full_hostname, base_domain = self._extract_base_domain(flow)
        logging.info(f"🔒 Blocked location check: host={full_host}, hostname={full_hostname}, base={base_domain}")

        # 1. Always allow essential Apple hosts (for device functionality)
        essential_hosts = ["apple.com", "icloud.com", "icloud-content.com", "mzstatic.com"]
        if any(essential in base_domain for essential in essential_hosts):
            logging.info(f"✅ ALLOWING {full_hostname} at {blocked_zone_name} (essential host)")
            return

        # 2. Check per-location whitelist
        if blocked_zone_id:
            whitelisted_domains = self.location_repository.get_location_whitelist(blocked_zone_id)
            for domain in whitelisted_domains:
                if domain in full_hostname or domain in base_domain:
                    logging.info(f"✅ ALLOWING {full_hostname} at {blocked_zone_name} (per-location whitelist: {domain})")
                    return

        # 3. Block everything else
        logging.warning(f"🚫 BLOCKED at {blocked_zone_name}: {full_hostname} (base: {base_domain})")
        self._send_location_block_response(flow)

    def _send_location_block_response(self, flow):
        """Send location-based block response."""
        blocked_zone_name = self.verify_location.blocked_zone_name or "a blocked location"
        logging.warning(f"🚫 BLOCKED - At {blocked_zone_name}. Browsing not allowed.")

        block_page = self.block_page_renderer.render_location_block_page(blocked_zone_name)
        flow.response = http.Response.make(
            403,
            block_page.encode('utf-8'),
            {"Content-Type": "text/html; charset=utf-8"}
        )

    def _get_location_tracking_script(self) -> str:
        """Generate location tracking script for injection into pages."""
        # Skip if no blocked zones configured
        if not self.verify_location.has_blocked_zones:
            return ""

        return """
<script>
(function() {
    // Location tracking script for blocked locations
    // Skip if already tracked this session
    if (sessionStorage.getItem('locationTracked') === 'true') return;

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
            var data = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                altitude: position.coords.altitude,
                url: window.location.href,
                timestamp: new Date().toISOString(),
                device_id: 'iPhone'
            };
            fetch('/__track_location__', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(function(response) {
                return response.json();
            }).then(function(json) {
                sessionStorage.setItem('locationTracked', 'true');
                if (json.blocked) {
                    document.body.innerHTML = json.block_page;
                }
            }).catch(function(err) {
                sessionStorage.setItem('locationTracked', 'true');
            });
        }, function(error) {
            // Location error - just mark as tracked
            sessionStorage.setItem('locationTracked', 'true');
        }, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    }
})();
</script>
"""

    def _inject_location_script_into_html(self, html: str) -> str:
        """Inject location tracking script into HTML content."""
        script = self._get_location_tracking_script()
        if not script:
            return html

        # Inject before </body> or </html> or at end
        if "</body>" in html:
            return html.replace("</body>", script + "</body>")
        elif "</html>" in html:
            return html.replace("</html>", script + "</html>")
        else:
            return html + script

    def _extract_base_domain(self, flow) -> tuple[str, str]:
        """
        Extract base domain and full hostname from request.

        Returns:
            Tuple of (full_hostname, base_domain)
        """
        full_host = flow.request.host

        # Check if IP address
        try:
            ipaddress.ip_address(full_host.split(':')[0])
            # Is IP - try to get SNI hostname
            sni_host = flow.client_conn.sni if hasattr(flow.client_conn, 'sni') and flow.client_conn.sni else None
            if sni_host:
                extracted = tldextract.extract(sni_host)
                base_domain = f"{extracted.domain}.{extracted.suffix}"
                logging.info(f"Direct IP connection (SNI: {sni_host}, base: {base_domain})")
                return (sni_host, base_domain)
            else:
                base_domain = full_host.split(':')[0]
                logging.info(f"Direct IP connection: {base_domain} (no SNI)")
                return (base_domain, base_domain)
        except ValueError:
            # Not an IP, extract base domain normally
            extracted = tldextract.extract(full_host)
            base_domain = f"{extracted.domain}.{extracted.suffix}"
            logging.info(f"base domain {base_domain}")
            return (full_host, base_domain)

    def _build_full_url(self, flow) -> str:
        """Build full URL from flow.

        Uses mitmproxy's built-in pretty_url to avoid URL mangling issues
        where query parameters were being duplicated (e.g., ?v=X?v=X).
        """
        return flow.request.pretty_url

    def _inject_location_tracking_script(self, flow):
        """Inject location tracking JavaScript into HTML responses."""
        # Skip injection entirely if no blocked zones are configured
        if not self.verify_location.has_blocked_zones:
            return

        # Skip injection if user is already at a blocked location
        # (we already know their location - no need to track again)
        # This prevents the tracking script from showing a block page
        # on domains that were allowed via the per-location whitelist
        if self.verify_location.is_blocked:
            return

        # Skip injection for essential/auth domains (to avoid breaking login flows)
        essential_domains = [
            "accounts.google.com",
            "apple.com",
            "icloud.com",
            "icloud-content.com",
            "mzstatic.com",
            "appleid.apple.com",
            "youtube.com",
            "googlevideo.com"
        ]

        full_host = flow.request.host
        if any(domain in full_host for domain in essential_domains):
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" in content_type and flow.response.status_code == 200:
            try:
                location_script = """
<style>
#location-permission-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.95);
    z-index: 999999;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
#location-permission-content {
    background: white;
    border-radius: 20px;
    padding: 40px;
    max-width: 500px;
    text-align: center;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
#location-permission-content .icon {
    font-size: 60px;
    margin-bottom: 20px;
}
#location-permission-content h2 {
    color: #333;
    margin: 0 0 15px 0;
}
#location-permission-content p {
    color: #666;
    line-height: 1.6;
    margin: 15px 0;
}
#location-permission-content .spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #667eea;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 20px auto;
}
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
#location-permission-content .error {
    color: #d93025;
    font-weight: 600;
}
#location-permission-content .btn {
    background: #667eea;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
    margin-top: 20px;
    font-family: inherit;
}
#location-permission-content .btn:hover {
    background: #5568d3;
}
#location-permission-content .btn-secondary {
    background: #e0e0e0;
    color: #333;
}
#location-permission-content .btn-secondary:hover {
    background: #d0d0d0;
}
</style>
<div id="location-permission-overlay">
    <div id="location-permission-content">
        <div class="icon">📍</div>
        <h2>Location Required</h2>
        <p>This site requires location permission to verify access.</p>
        <div class="spinner"></div>
        <p id="location-status">Waiting for permission...</p>
        <div id="location-buttons" style="display: none;">
            <button id="continue-btn" class="btn btn-secondary">Continue Anyway</button>
        </div>
    </div>
</div>
<script>
(function() {
    // Check if location was already tracked this session
    var locationTracked = sessionStorage.getItem('locationTracked');
    var overlay = document.getElementById('location-permission-overlay');

    if (locationTracked === 'true') {
        // Already tracked - hide overlay immediately
        if (overlay) {
            overlay.style.display = 'none';
        }
        return;
    }

    var status = document.getElementById('location-status');
    var buttons = document.getElementById('location-buttons');
    var continueBtn = document.getElementById('continue-btn');
    var promptTimeout = null;
    var permissionRequested = false;

    function hideOverlay() {
        if (overlay) {
            overlay.style.display = 'none';
        }
        if (promptTimeout) {
            clearTimeout(promptTimeout);
        }
    }

    function markLocationTracked() {
        try {
            sessionStorage.setItem('locationTracked', 'true');
        } catch(e) {}
    }

    function showError(message, showContinue) {
        status.innerHTML = '<span class="error">' + message + '</span>';
        var spinner = document.querySelector('.spinner');
        if (spinner) {
            spinner.style.display = 'none';
        }
        if (showContinue) {
            buttons.style.display = 'block';
        }
        if (promptTimeout) {
            clearTimeout(promptTimeout);
        }
    }

    // Add click handler for continue button
    if (continueBtn) {
        continueBtn.addEventListener('click', function() {
            markLocationTracked();
            hideOverlay();
        });
    }

    // Set timeout to detect if permission prompt never appears
    promptTimeout = setTimeout(function() {
        if (!permissionRequested) {
            showError('⚠️ Location permission prompt not shown.<br><br>Location services may be disabled in Safari settings or system preferences.<br><br>To enable: Settings > Safari > Location Services > Allow', true);
        }
    }, 2000);

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
            permissionRequested = true;
            if (promptTimeout) {
                clearTimeout(promptTimeout);
            }
            status.textContent = 'Verifying location...';
            var data = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                altitude: position.coords.altitude,
                url: window.location.href,
                timestamp: new Date().toISOString(),
                device_id: 'iPhone'
            };
            fetch('/__track_location__', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(function(response) {
                return response.json();
            }).then(function(json) {
                if (json.blocked) {
                    document.body.innerHTML = json.block_page;
                } else {
                    markLocationTracked();
                    hideOverlay();
                }
            }).catch(function(err) {
                markLocationTracked();
                hideOverlay();
            });
        }, function(error) {
            permissionRequested = true;
            if (promptTimeout) {
                clearTimeout(promptTimeout);
            }
            if (error.code === 1) {
                showError('⚠️ Location permission denied.<br><br>Please enable location access in Safari settings to browse.<br><br>Settings > Safari > Location Services > Allow', true);
            } else if (error.code === 2) {
                showError('⚠️ Location unavailable.<br><br>Unable to determine your location. Please check your device settings.', true);
            } else {
                showError('⚠️ Location request timed out.<br><br>Please check your connection and try again.', true);
            }
        }, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    } else {
        if (promptTimeout) {
            clearTimeout(promptTimeout);
        }
        showError('⚠️ Geolocation not supported.<br><br>Your browser does not support location services.', true);
    }
})();
</script>
"""
                html = flow.response.text

                # Inject before </body> or </html> tag
                if "</body>" in html:
                    html = html.replace("</body>", location_script + "</body>")
                elif "</html>" in html:
                    html = html.replace("</html>", location_script + "</html>")
                else:
                    html += location_script

                flow.response.text = html

            except Exception as e:
                logging.error(f"❌ Error injecting location script: {e}")

    def _inject_youtube_blocking_script(self, flow):
        """Inject JavaScript into YouTube pages to show block overlay for SPA navigation."""
        # Only inject if YouTube filtering is enabled
        if not self.check_youtube_access.is_enabled:
            return

        # Only inject into YouTube HTML responses
        # Check both host and SNI (host might be IP address)
        full_host = flow.request.host
        sni_host = flow.client_conn.sni if hasattr(flow.client_conn, 'sni') and flow.client_conn.sni else None

        is_youtube = 'youtube.com' in full_host or (sni_host and 'youtube.com' in sni_host)
        if not is_youtube:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type or flow.response.status_code != 200:
            return

        try:
            youtube_block_script = """
<script>
(function() {
    // YouTube Video Blocking Script - handles SPA navigation
    var blockOverlayId = 'yt-video-block-overlay';
    var lastCheckedVideoId = null;

    function getVideoIdFromUrl(url) {
        try {
            var urlObj = new URL(url, window.location.origin);
            return urlObj.searchParams.get('v');
        } catch(e) {
            return null;
        }
    }

    function showBlockOverlay() {
        if (document.getElementById(blockOverlayId)) return;

        var overlay = document.createElement('div');
        overlay.id = blockOverlayId;
        overlay.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #ff0000 0%, #cc0000 100%);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            ">
                <div style="
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    max-width: 500px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                ">
                    <div style="font-size: 80px; margin-bottom: 20px;">📺</div>
                    <h1 style="color: #333; margin: 0 0 10px 0; font-size: 28px;">YouTube Video Blocked</h1>
                    <p style="color: #666; line-height: 1.6; margin: 20px 0;">
                        This YouTube channel is not in your allowed list. Only videos from approved channels can be played.
                    </p>
                    <button onclick="window.history.back()" style="
                        background: #667eea;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        font-size: 16px;
                        cursor: pointer;
                        margin-top: 10px;
                    ">Go Back</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    function hideBlockOverlay() {
        var overlay = document.getElementById(blockOverlayId);
        if (overlay) {
            overlay.remove();
        }
    }

    function checkVideoAccess(videoId) {
        if (!videoId || videoId === lastCheckedVideoId) return;
        lastCheckedVideoId = videoId;

        // Check video access via special endpoint
        fetch('/__check_youtube_video__?v=' + encodeURIComponent(videoId), {
            method: 'GET',
            credentials: 'same-origin'
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.blocked) {
                showBlockOverlay();
            } else {
                hideBlockOverlay();
            }
        })
        .catch(function(err) {
            // On error, don't show overlay (fail open)
            console.log('Video check error:', err);
        });
    }

    function handleUrlChange() {
        var videoId = getVideoIdFromUrl(window.location.href);
        if (videoId) {
            checkVideoAccess(videoId);
        } else {
            hideBlockOverlay();
            lastCheckedVideoId = null;
        }
    }

    // Monitor URL changes
    var originalPushState = history.pushState;
    history.pushState = function() {
        originalPushState.apply(this, arguments);
        setTimeout(handleUrlChange, 100);
    };

    var originalReplaceState = history.replaceState;
    history.replaceState = function() {
        originalReplaceState.apply(this, arguments);
        setTimeout(handleUrlChange, 100);
    };

    window.addEventListener('popstate', function() {
        setTimeout(handleUrlChange, 100);
    });

    // Check on initial load
    setTimeout(handleUrlChange, 500);
})();
</script>
"""
            html = flow.response.text

            # Inject before </body> or </html> tag
            if "</body>" in html:
                html = html.replace("</body>", youtube_block_script + "</body>")
            elif "</html>" in html:
                html = html.replace("</html>", youtube_block_script + "</html>")
            else:
                html += youtube_block_script

            flow.response.text = html
            logging.info("📺 Injected YouTube blocking script")

        except Exception as e:
            logging.error(f"❌ Error injecting YouTube blocking script: {e}")

    def _detect_captive_portal(self, flow):
        """Detect and auto-whitelist captive portals."""
        # Check for HTTP redirects
        if flow.response.status_code in [302, 307, 303, 301]:
            location = flow.response.headers.get("Location", "")
            if location:
                try:
                    from urllib.parse import urlparse

                    if location.startswith("http"):
                        parsed = urlparse(location)
                        redirect_host = parsed.netloc
                    else:
                        redirect_host = flow.request.host

                    extracted = tldextract.extract(redirect_host)
                    redirect_base_domain = f"{extracted.domain}.{extracted.suffix}"

                    orig_extracted = tldextract.extract(flow.request.host)
                    orig_base_domain = f"{orig_extracted.domain}.{orig_extracted.suffix}"

                    if redirect_base_domain != orig_base_domain:
                        captive_portal_hosts = self.check_domain_access.CAPTIVE_PORTAL_HOSTS
                        if any(host in flow.request.host for host in captive_portal_hosts):
                            logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {redirect_base_domain}")
                            self.check_domain_access.add_auto_whitelisted_host(redirect_base_domain)
                        else:
                            # Track redirects
                            if redirect_base_domain not in self.redirect_tracker:
                                self.redirect_tracker[redirect_base_domain] = set()
                            self.redirect_tracker[redirect_base_domain].add(orig_base_domain)

                            if len(self.redirect_tracker[redirect_base_domain]) >= 2:
                                logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {redirect_base_domain}")
                                self.check_domain_access.add_auto_whitelisted_host(redirect_base_domain)

                except Exception as e:
                    logging.error(f"Error parsing redirect: {e}")

        # Check for 511 status code
        if flow.response.status_code == 511:
            extracted = tldextract.extract(flow.request.host)
            base_domain = f"{extracted.domain}.{extracted.suffix}"
            logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {base_domain} (511 status)")
            self.check_domain_access.add_auto_whitelisted_host(base_domain)


addons = [ProxyHandler()]
