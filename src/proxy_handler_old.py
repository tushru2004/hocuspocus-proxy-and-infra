"""
Mitmproxy addon for traffic filtering, location tracking, and content blocking.

Handles:
- Domain whitelisting/blocking
- YouTube channel filtering
- GPS location tracking and location-based blocking
- Custom block pages

Run as follows: mitmproxy -s proxy_handler.py
"""
import re
import logging
import os
from mitmproxy import ctx, http
import tldextract
import psycopg
from psycopg.rows import dict_row
from urllib.parse import urlparse, parse_qs
import requests
import json

class Counter:
    def __init__(self):
        self.num = 0
        # Dynamic list for auto-detected captive portals
        self.auto_whitelisted_hosts = set()
        self.redirect_tracker = {}  # Track redirects to detect captive portals

        # Database connection details (from environment variables)
        self.db_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.db_port = os.getenv('POSTGRES_PORT', '5432')
        self.db_name = os.getenv('POSTGRES_DB', 'mitmproxy')
        self.db_user = os.getenv('POSTGRES_USER', 'mitmproxy')
        self.db_password = os.getenv('POSTGRES_PASSWORD', 'mitmproxy')

        # YouTube filtering
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY', '')
        self.video_to_channel_cache = {}  # Cache video_id -> channel_id mapping
        self.allowed_youtube_channels = []  # Loaded from database
        self.youtube_filter_enabled = False

        # Location-based blocking
        self.currently_at_blocked_location = False
        self.current_blocked_location_name = None
        self.last_location_check = None

    # Blocked locations: Browsing is ONLY allowed when NOT at these locations
    BLOCKED_LOCATIONS = [
        {
            'latitude': 48.1785,  # GPS coordinates for Mautner-Markhof-Gasse 11
            'longitude': 16.4207,
            'radius_meters': 100,  # Block if within 100 meters
            'name': 'Mautner-Markhof-Gasse 11/11, Vienna, Austria, 1110'
        },
        {
            'latitude': 48.20028,  # GPS coordinates for Phil Cafe
            'longitude': 16.36116,
            'radius_meters': 100,  # Block if within 100 meters
            'name': 'Phil Cafe, Gumpendorfer Str. 10-12, 1060 Wien'
        }
    ]

    # Essential hosts that must always work (iOS functionality, WiFi login)
    ESSENTIAL_HOSTS = ["apple.com", "icloud.com", "icloud-content.com", "mzstatic.com"]

    # Whitelist: Loaded from PostgreSQL (fallback if DB unavailable)
    ALLOWED_HOSTS = ["amazon.com"]

    def load_allowed_hosts_from_db(self):
        """Load allowed hosts from PostgreSQL database"""
        try:
            # Connect to PostgreSQL using psycopg (v3)
            conn_string = f"host={self.db_host} port={self.db_port} dbname={self.db_name} user={self.db_user} password={self.db_password}"
            with psycopg.connect(conn_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    # Query enabled allowed hosts
                    cursor.execute("SELECT domain FROM allowed_hosts WHERE enabled = true")
                    rows = cursor.fetchall()

                    # Update ALLOWED_HOSTS list
                    self.ALLOWED_HOSTS = [row['domain'] for row in rows]

                    logging.info(f"✅ Loaded {len(self.ALLOWED_HOSTS)} allowed hosts from database: {self.ALLOWED_HOSTS}")

        except Exception as e:
            logging.error(f"❌ Failed to load allowed hosts from database: {e}")
            logging.info(f"Using fallback allowed hosts: {self.ALLOWED_HOSTS}")

    def load_allowed_youtube_channels_from_db(self):
        """Load allowed YouTube channels from PostgreSQL database"""
        try:
            conn_string = f"host={self.db_host} port={self.db_port} dbname={self.db_name} user={self.db_user} password={self.db_password}"
            with psycopg.connect(conn_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    # Query enabled YouTube channels
                    cursor.execute("SELECT channel_id, channel_name FROM youtube_channels WHERE enabled = true")
                    rows = cursor.fetchall()

                    # Update allowed channels list
                    self.allowed_youtube_channels = [row['channel_id'] for row in rows]
                    self.youtube_filter_enabled = len(self.allowed_youtube_channels) > 0

                    if self.youtube_filter_enabled:
                        channel_names = [row['channel_name'] for row in rows]
                        logging.info(f"✅ YouTube filtering ENABLED for {len(self.allowed_youtube_channels)} channels: {channel_names}")
                    else:
                        logging.info("ℹ️  YouTube filtering DISABLED (no channels configured)")

        except Exception as e:
            logging.error(f"❌ Failed to load YouTube channels from database: {e}")
            self.youtube_filter_enabled = False

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two GPS coordinates in meters using Haversine formula"""
        from math import radians, sin, cos, sqrt, atan2

        # Earth radius in meters
        R = 6371000

        # Convert to radians
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)

        # Haversine formula
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c

        return distance

    def is_at_blocked_location(self, latitude, longitude):
        """Check if current location is within any blocked location radius
        Returns: (is_blocked, location_info, distance) tuple
        """
        for location in self.BLOCKED_LOCATIONS:
            distance = self.calculate_distance(
                latitude, longitude,
                location['latitude'],
                location['longitude']
            )
            if distance <= location['radius_meters']:
                return (True, location, distance)
        return (False, None, None)

    def store_location(self, latitude, longitude, url, timestamp, accuracy=None, altitude=None, device_id='iPhone'):
        """Store location data in PostgreSQL database and update blocking status"""
        try:
            # Check if at any blocked location
            is_blocked, blocked_location, distance = self.is_at_blocked_location(latitude, longitude)

            # Update blocking status
            self.currently_at_blocked_location = is_blocked
            self.current_blocked_location_name = blocked_location['name'] if is_blocked else None
            self.last_location_check = timestamp

            # Log blocking status
            if is_blocked:
                logging.warning(f"🚫 BLOCKING ENABLED - You are at blocked location ({blocked_location['name']}) - {distance:.0f}m away")
            else:
                logging.info(f"✅ Browsing allowed - Not at any blocked location")

            # Store in database
            conn_string = f"host={self.db_host} port={self.db_port} dbname={self.db_name} user={self.db_user} password={self.db_password}"
            with psycopg.connect(conn_string) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO locations (device_id, latitude, longitude, accuracy, altitude, url, timestamp)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (device_id, latitude, longitude, accuracy, altitude, url, timestamp)
                    )
                    conn.commit()
                    logging.info(f"📍 Location stored: {latitude}, {longitude} for {url}")
        except Exception as e:
            logging.error(f"❌ Failed to store location: {e}")

    def extract_youtube_video_id(self, url):
        """Extract YouTube video ID from URL"""
        try:
            # Handle different YouTube URL formats:
            # - https://www.youtube.com/watch?v=VIDEO_ID
            # - https://youtu.be/VIDEO_ID
            # - https://m.youtube.com/watch?v=VIDEO_ID
            # - https://m.youtube.com/api/stats/watchtime?...&docid=VIDEO_ID (mobile)

            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Check for 'v' parameter (desktop/mobile watch page)
            if 'v' in query_params:
                return query_params['v'][0]

            # Check for 'docid' parameter (mobile API calls)
            if 'docid' in query_params:
                return query_params['docid'][0]

            # Check for youtu.be short URL
            if 'youtu.be/' in url:
                return parsed.path.strip('/')

            return None
        except Exception as e:
            logging.error(f"Error extracting video ID from {url}: {e}")
            return None

    def get_channel_id_from_video(self, video_id):
        """Get YouTube channel ID from video ID using YouTube Data API"""
        # Check cache first
        if video_id in self.video_to_channel_cache:
            return self.video_to_channel_cache[video_id]

        if not self.youtube_api_key:
            logging.warning("YouTube API key not configured, cannot verify channel")
            return None

        try:
            # Call YouTube Data API
            api_url = f"https://www.googleapis.com/youtube/v3/videos"
            params = {
                'part': 'snippet',
                'id': video_id,
                'key': self.youtube_api_key
            }

            response = requests.get(api_url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if 'items' in data and len(data['items']) > 0:
                    channel_id = data['items'][0]['snippet']['channelId']
                    channel_title = data['items'][0]['snippet']['channelTitle']

                    # Cache the result
                    self.video_to_channel_cache[video_id] = channel_id

                    logging.info(f"📺 Video {video_id} belongs to channel: {channel_title} ({channel_id})")
                    return channel_id
            else:
                logging.error(f"YouTube API error: {response.status_code}")

        except Exception as e:
            logging.error(f"Error calling YouTube API: {e}")

        return None

    def is_youtube_video_allowed(self, url):
        """Check if a YouTube video URL is allowed based on channel whitelist"""
        video_id = self.extract_youtube_video_id(url)
        if not video_id:
            return True  # Not a video URL, allow it

        channel_id = self.get_channel_id_from_video(video_id)
        if not channel_id:
            logging.warning(f"⚠️  Could not determine channel for video {video_id}, BLOCKING by default")
            return False

        if channel_id in self.allowed_youtube_channels:
            logging.info(f"✅ ALLOWING video {video_id} (channel {channel_id} is whitelisted)")
            return True
        else:
            logging.info(f"🚫 BLOCKING video {video_id} (channel {channel_id} not in whitelist)")
            return False

    # Known captive portal detection URLs used by operating systems
    CAPTIVE_PORTAL_DETECTION_HOSTS = [
        "captive.apple.com",
        "connectivitycheck.gstatic.com",
        "clients3.google.com",
        "msftconnecttest.com",
        "detectportal.firefox.com",
        "nmcheck.gnome.org",
        "network-test.debian.org",
    ]

    def request(self, flow):
        self.num = self.num + 1
        logging.info("We've seen %d flows" % self.num)
        logging.info(f"Request URL: {flow.request.host}")

        # Handle location tracking endpoint (intercept special path on any domain)
        if flow.request.path == "/__track_location__" and flow.request.method == "POST":
            logging.info(f"📍 Received location tracking request from {flow.request.host}")
            try:
                # Parse JSON body
                data = json.loads(flow.request.content)

                latitude = data.get('latitude')
                longitude = data.get('longitude')
                url = data.get('url', 'unknown')
                timestamp = data.get('timestamp')
                accuracy = data.get('accuracy')
                altitude = data.get('altitude')
                device_id = data.get('device_id', 'iPhone')

                # Store in database (this also updates self.currently_at_blocked_location)
                self.store_location(latitude, longitude, url, timestamp, accuracy, altitude, device_id)

                # Check if now at blocked location
                response_data = {
                    "status": "ok",
                    "blocked": self.currently_at_blocked_location
                }

                # If blocked, include the block page HTML
                if self.currently_at_blocked_location:
                    blocked_location_name = self.current_blocked_location_name or "a blocked location"
                    response_data["block_page"] = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browsing Blocked</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .emoji {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .location {{
            color: #666;
            font-size: 16px;
            margin: 10px 0 20px 0;
        }}
        p {{
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }}
        .note {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">🚫</div>
        <h1>Browsing Blocked</h1>
        <div class="location">📍 {blocked_location_name}</div>
        <p>You are currently at a blocked location. Internet browsing is not allowed at this location.</p>
        <p>To browse websites, please move to a different location.</p>
        <div class="note">
            <strong>Note:</strong> Essential services (Apple, iCloud) remain accessible.
        </div>
    </div>
</body>
</html>
"""

                # Return response (intercepted, never forwarded to real server)
                flow.response = http.Response.make(
                    200,
                    json.dumps(response_data).encode('utf-8'),
                    {"Content-Type": "application/json"}
                )
                return
            except Exception as e:
                logging.error(f"❌ Error processing location: {e}")
                flow.response = http.Response.make(
                    400,
                    b'{"status": "error"}',
                    {"Content-Type": "application/json"}
                )
                return

        full_host = flow.request.host

        # Location-based blocking: Block all browsing if at blocked location
        # Always allow essential hosts (Apple services) regardless of location
        extracted_for_essential = tldextract.extract(full_host)
        base_domain_for_essential = f"{extracted_for_essential.domain}.{extracted_for_essential.suffix}"
        is_essential_host = any(essential_host in base_domain_for_essential for essential_host in self.ESSENTIAL_HOSTS)

        if self.currently_at_blocked_location and not is_essential_host:
            blocked_location_name = self.current_blocked_location_name or "a blocked location"
            logging.warning(f"🚫 BLOCKED - You are at {blocked_location_name}. Browsing not allowed at this location.")
            flow.response = http.Response.make(
                403,
                f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browsing Blocked</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .emoji {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .location {{
            color: #666;
            font-size: 16px;
            margin: 10px 0 20px 0;
        }}
        p {{
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }}
        .note {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">🚫</div>
        <h1>Browsing Blocked</h1>
        <div class="location">📍 {blocked_location_name}</div>
        <p>You are currently at a blocked location. Internet browsing is not allowed at this location.</p>
        <p>To browse websites, please move to a different location.</p>
        <div class="note">
            <strong>Note:</strong> Essential services (Apple, iCloud) remain accessible.
        </div>
    </div>
</body>
</html>""".encode('utf-8'),
                {"Content-Type": "text/html; charset=utf-8"}
            )
            return

        # Check if host is an IP address
        import ipaddress
        is_ip = False
        try:
            ipaddress.ip_address(full_host.split(':')[0])  # Remove port if present
            is_ip = True
        except ValueError:
            pass

        if is_ip:
            # For IP addresses, try to get the SNI hostname for whitelist checking
            sni_host = flow.client_conn.sni if hasattr(flow.client_conn, 'sni') and flow.client_conn.sni else None
            if sni_host:
                # Use SNI hostname for whitelist checking
                full_host = sni_host
                extracted = tldextract.extract(sni_host)
                base_domain = f"{extracted.domain}.{extracted.suffix}"
                logging.info(f"Direct IP connection to {full_host.split(':')[0]} (SNI: {sni_host}, base: {base_domain})")
            else:
                # No SNI, use IP address
                base_domain = full_host.split(':')[0]
                logging.info(f"Direct IP connection: {base_domain} (no SNI)")
        else:
            # For domain names, extract base domain
            extracted = tldextract.extract(full_host)
            base_domain = f"{extracted.domain}.{extracted.suffix}"
            logging.info(f"base domain {base_domain}")

        # WHITELIST MODE: Only allow specific domains, block everything else

        # 1. Always allow captive portal detection URLs (critical for WiFi login)
        if any(detection_host in full_host for detection_host in self.CAPTIVE_PORTAL_DETECTION_HOSTS):
            logging.info(f"✅ Allowing captive portal detection URL: {full_host}")
            pass  # Let request go through naturally

        # 2. Allow auto-detected captive portals (critical for WiFi login)
        # EXCLUDE youtube.com from auto-captive portal to allow channel filtering
        elif base_domain in self.auto_whitelisted_hosts and base_domain != 'youtube.com':
            logging.info(f"✅ Allowing auto-detected captive portal: {base_domain}")
            pass  # Let request go through naturally

        # 3. Allow essential hosts (Apple services - required for iPhone to function)
        elif base_domain in self.ESSENTIAL_HOSTS:
            logging.info(f"✅ Allowing essential host: {base_domain}")
            pass  # Let request go through naturally

        # 4. Allow whitelisted domains and related subdomains
        # Check if any allowed domain is part of the current domain (e.g., images-amazon.com contains "amazon")
        elif any(allowed in full_host for allowed in self.ALLOWED_HOSTS):
            # Special handling for YouTube: check channel whitelist if enabled
            if self.youtube_filter_enabled and 'youtube.com' in full_host:
                # Build full URL properly
                full_url = f"{flow.request.scheme}://{flow.request.host}{flow.request.path}"
                if flow.request.query:
                    # Convert query MultiDict to proper query string
                    from urllib.parse import urlencode
                    query_string = urlencode(flow.request.query.fields)
                    full_url += f"?{query_string}"

                logging.info(f"🔍 Checking YouTube URL: {full_url}")

                # Check if this is a video URL and if it's allowed
                if not self.is_youtube_video_allowed(full_url):
                    logging.info(f"🚫 BLOCKING YouTube video (channel not whitelisted)")
                    flow.response = http.Response.make(
                        403,
                        b"Access denied: This YouTube channel is not allowed",
                        {"Content-Type": "text/plain"}
                    )
                    return

            logging.info(f"✅ Allowing whitelisted domain: {full_host} (matches {[a for a in self.ALLOWED_HOSTS if a in full_host]})")
            pass  # Let request go through naturally

        # 5. BLOCK everything else
        else:
            logging.info(f"🚫 BLOCKING non-whitelisted domain: {base_domain}")

            flow.response = http.Response.make(
                403,  # Forbidden status code
                b"Access denied: Only whitelisted domains are allowed",
                {"Content-Type": "text/plain"}
            )
            return

    def response(self, flow):
        """Detect captive portals by analyzing redirects and inject location tracking"""
        if not flow.response:
            return

        # Inject location tracking JavaScript into HTML responses
        content_type = flow.response.headers.get("content-type", "")
        if "text/html" in content_type and flow.response.status_code == 200:
            try:
                # JavaScript to capture and send location with permission enforcement
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
</style>
<div id="location-permission-overlay">
    <div id="location-permission-content">
        <div class="icon">📍</div>
        <h2>Location Required</h2>
        <p>This site requires location permission to verify access.</p>
        <div class="spinner"></div>
        <p id="location-status">Waiting for permission...</p>
    </div>
</div>
<script>
(function() {
    var overlay = document.getElementById('location-permission-overlay');
    var status = document.getElementById('location-status');

    function hideOverlay() {
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    function showError(message) {
        status.innerHTML = '<span class="error">' + message + '</span>';
        document.querySelector('.spinner').style.display = 'none';
    }

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
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
                    // At blocked location - replace page with block message
                    document.body.innerHTML = json.block_page;
                } else {
                    // Not at blocked location - hide overlay and show page
                    hideOverlay();
                }
            }).catch(function(err) {
                // Network error - allow page to show (fail open)
                hideOverlay();
            });
        }, function(error) {
            if (error.code === 1) {
                showError('⚠️ Location permission denied.<br><br>You must grant location permission to browse websites.<br><br>Please refresh and allow location access.');
            } else if (error.code === 2) {
                showError('⚠️ Location unavailable.<br><br>Unable to determine your location. Please check your device settings.');
            } else {
                showError('⚠️ Location request timed out.<br><br>Please refresh the page to try again.');
            }
        }, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    } else {
        showError('⚠️ Geolocation not supported.<br><br>Your browser does not support location services.');
    }
})();
</script>
"""
                # Decode response (handles gzip/brotli automatically)
                # Work with text to avoid issues with compressed content
                html = flow.response.text

                # Inject before </body> or </html> tag
                if "</body>" in html:
                    html = html.replace("</body>", location_script + "</body>")
                elif "</html>" in html:
                    html = html.replace("</html>", location_script + "</html>")
                else:
                    # If no closing tags, append at the end
                    html += location_script

                # Set the modified text back (mitmproxy handles encoding automatically)
                flow.response.text = html

            except Exception as e:
                logging.error(f"❌ Error injecting location script: {e}")

        # Check for HTTP redirects (302, 307, etc.)
        if flow.response.status_code in [302, 307, 303, 301]:
            location = flow.response.headers.get("Location", "")
            if location:
                # Extract the redirect destination domain
                try:
                    # Handle both absolute and relative URLs
                    if location.startswith("http"):
                        from urllib.parse import urlparse
                        parsed = urlparse(location)
                        redirect_host = parsed.netloc
                    else:
                        # Relative redirect, use current host
                        redirect_host = flow.request.host

                    # Extract base domain
                    extracted = tldextract.extract(redirect_host)
                    redirect_base_domain = f"{extracted.domain}.{extracted.suffix}"

                    # Extract original request domain
                    orig_extracted = tldextract.extract(flow.request.host)
                    orig_base_domain = f"{orig_extracted.domain}.{orig_extracted.suffix}"

                    # If redirecting to a different domain, it might be a captive portal
                    if redirect_base_domain != orig_base_domain:
                        # Check if the original request was to a captive portal detection URL
                        if any(detection_host in flow.request.host for detection_host in self.CAPTIVE_PORTAL_DETECTION_HOSTS):
                            logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {redirect_base_domain} (from detection URL)")
                            self.auto_whitelisted_hosts.add(redirect_base_domain)
                        else:
                            # Track suspicious redirects
                            if redirect_base_domain not in self.redirect_tracker:
                                self.redirect_tracker[redirect_base_domain] = set()
                            self.redirect_tracker[redirect_base_domain].add(orig_base_domain)

                            # If the same domain redirects multiple different destinations, it's likely a captive portal
                            if len(self.redirect_tracker[redirect_base_domain]) >= 2:
                                logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {redirect_base_domain} (multiple redirects)")
                                self.auto_whitelisted_hosts.add(redirect_base_domain)

                except Exception as e:
                    logging.error(f"Error parsing redirect: {e}")

        # Check for captive portal specific status code
        if flow.response.status_code == 511:  # Network Authentication Required
            extracted = tldextract.extract(flow.request.host)
            base_domain = f"{extracted.domain}.{extracted.suffix}"
            logging.info(f"🌐 CAPTIVE PORTAL DETECTED: {base_domain} (511 status)")
            self.auto_whitelisted_hosts.add(base_domain)

    def load(self, loader):
        # Load allowed hosts from PostgreSQL database
        self.load_allowed_hosts_from_db()

        # Load allowed YouTube channels from PostgreSQL database
        self.load_allowed_youtube_channels_from_db()

        # Load default ignore hosts from a file
        #default_ignore_hosts = self.load_ignore_hosts_from_file("ignore_hosts.txt")

        # Load default ignore hosts from a file
        loader.add_option(
            name="block_global",
            typespec=bool,
            default=False,
            help="Disable block global option",
        )
    # def load_ignore_hosts_from_file(self, file_path):
    #     """
    #     Load ignore hosts from the specified file and return them as a space-separated string.
    #     """
    #     try:
    #         with open(file_path, "r") as file:
    #             domains = [line.strip() for line in file if line.strip()]
    #             ctx.log.info(f"Loaded ignore hosts from {file_path}: {domains}")
    #             self.ignore_hosts_patterns = [re.compile(pattern) for pattern in domains]
    #             return " ".join(domains)
    #     except FileNotFoundError:
    #         ctx.log.warning(f"Ignore hosts file not found: {file_path}. Using default patterns.")
    #         self.ignore_hosts_patterns = [re.compile(pattern) for pattern in ["icloud.com", "apple.com", "mzstatic.com"]]
    #         return "icloud.com apple.com mzstatic.com"
addons = [Counter()]