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

        # Get services
        self.block_page_renderer = self.container.get_block_page_renderer()

        # Captive portal tracking
        self.redirect_tracker = {}

    def request(self, flow):
        """Handle incoming requests."""
        self.num += 1
        logging.info(f"We've seen {self.num} flows")
        logging.info(f"Request URL: {flow.request.host}")

        # Handle location tracking endpoint
        if flow.request.path == "/__track_location__" and flow.request.method == "POST":
            self._handle_location_tracking(flow)
            return

        full_host = flow.request.host

        # Check location-based blocking first
        if self._should_block_due_to_location(full_host):
            self._send_location_block_response(flow)
            return

        # Extract full hostname and base domain
        full_hostname, base_domain = self._extract_base_domain(flow)

        # Check domain access (pass both full hostname and base domain)
        decision = self.check_domain_access.execute(full_hostname, base_domain)

        if decision.allowed:
            # Special handling for YouTube
            if self.check_youtube_access.is_enabled and 'youtube.com' in full_hostname:
                youtube_url = self._build_full_url(flow)
                logging.info(f"🔍 Checking YouTube URL: {youtube_url}")
                youtube_decision = self.check_youtube_access.execute(youtube_url)

                if not youtube_decision.allowed:
                    logging.info("🚫 BLOCKING YouTube video (channel not whitelisted)")
                    flow.response = http.Response.make(
                        403,
                        b"Access denied: This YouTube channel is not allowed",
                        {"Content-Type": "text/plain"}
                    )
                    return
                else:
                    logging.info(f"✅ YouTube check passed: {youtube_url}")

            logging.info(f"✅ Allowing: {full_hostname} (host: {full_host})")
        else:
            # Block
            logging.info(f"🚫 BLOCKING: {base_domain} - {decision.message}")
            block_page = self.block_page_renderer.render_domain_block_page(base_domain)
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

    def _should_block_due_to_location(self, host: str) -> bool:
        """Check if request should be blocked due to location."""
        # Always allow essential hosts
        extracted = tldextract.extract(host)
        base_domain = f"{extracted.domain}.{extracted.suffix}"

        essential_hosts = ["apple.com", "icloud.com", "icloud-content.com", "mzstatic.com"]
        is_essential = any(essential in base_domain for essential in essential_hosts)

        return self.verify_location.is_blocked and not is_essential

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
        """Build full URL from flow."""
        full_url = f"{flow.request.scheme}://{flow.request.host}{flow.request.path}"
        if flow.request.query:
            query_string = urlencode(flow.request.query.fields)
            full_url += f"?{query_string}"
        return full_url

    def _inject_location_tracking_script(self, flow):
        """Inject location tracking JavaScript into HTML responses."""
        # Skip injection for essential/auth domains
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
    var overlay = document.getElementById('location-permission-overlay');
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
                    hideOverlay();
                }
            }).catch(function(err) {
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
