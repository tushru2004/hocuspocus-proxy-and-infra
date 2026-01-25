#!/usr/bin/env python3
"""
macOS Location Sender

Periodically sends device location to the VPN proxy.
Uses CoreLocation via pyobjc to get GPS coordinates.

Install dependencies:
    pip3 install pyobjc-framework-CoreLocation requests

Grant location permissions:
    System Settings > Privacy & Security > Location Services > Enable for Python/Terminal

Usage:
    python3 location_sender.py

Run as LaunchAgent for continuous operation (see com.hocuspocus.location-sender.plist)
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
# Use any domain that routes through VPN - the proxy intercepts /__track_location__ path
PROXY_URL = os.environ.get('PROXY_URL', 'http://google.com/__track_location__')
DEVICE_ID = os.environ.get('DEVICE_ID', '2162127')  # MacBook Air SimpleMDM ID
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '30'))

# CoreLocation imports (macOS only)
try:
    import objc
    from CoreLocation import (
        CLLocationManager,
        CLLocation,
        kCLLocationAccuracyBest,
        kCLAuthorizationStatusAuthorizedAlways,
        kCLAuthorizationStatusAuthorized,
    )
    from Foundation import NSObject, NSRunLoop, NSDate
    CORELOCATION_AVAILABLE = True
except ImportError:
    logger.warning("CoreLocation not available. Install pyobjc-framework-CoreLocation")
    CORELOCATION_AVAILABLE = False


class LocationDelegate(NSObject):
    """Delegate for CLLocationManager callbacks."""

    def init(self):
        self = objc.super(LocationDelegate, self).init()
        if self is None:
            return None
        self.location = None
        self.error = None
        self.updated = False
        return self

    def locationManager_didUpdateLocations_(self, manager, locations):
        """Called when location is updated."""
        if locations and len(locations) > 0:
            self.location = locations[-1]  # Most recent location
            self.updated = True
            logger.debug(f"Location updated: {self.location.coordinate().latitude}, {self.location.coordinate().longitude}")

    def locationManager_didFailWithError_(self, manager, error):
        """Called when location update fails."""
        self.error = error
        self.updated = True
        logger.error(f"Location error: {error}")

    def locationManager_didChangeAuthorizationStatus_(self, manager, status):
        """Called when authorization status changes."""
        status_names = {
            0: "Not Determined",
            1: "Restricted",
            2: "Denied",
            3: "Authorized Always",
            4: "Authorized When In Use"
        }
        logger.info(f"Authorization status: {status_names.get(status, status)}")


def get_location_corelocation(timeout=10):
    """Get location using CoreLocation (macOS)."""
    if not CORELOCATION_AVAILABLE:
        return None

    manager = CLLocationManager.alloc().init()
    delegate = LocationDelegate.alloc().init()
    manager.setDelegate_(delegate)
    manager.setDesiredAccuracy_(kCLLocationAccuracyBest)

    # Request authorization if needed
    auth_status = CLLocationManager.authorizationStatus()
    logger.debug(f"Current auth status: {auth_status}")

    if auth_status == 0:  # Not determined
        logger.info("Requesting location authorization...")
        # Note: For command-line tools, authorization is typically inherited from Terminal

    # Start location updates
    manager.startUpdatingLocation()

    # Wait for location with timeout
    start_time = time.time()
    while not delegate.updated and (time.time() - start_time) < timeout:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )

    manager.stopUpdatingLocation()

    if delegate.location:
        coord = delegate.location.coordinate()
        return {
            'latitude': coord.latitude,
            'longitude': coord.longitude,
            'accuracy': delegate.location.horizontalAccuracy(),
            'altitude': delegate.location.altitude(),
            'timestamp': datetime.now().isoformat()
        }
    elif delegate.error:
        logger.error(f"Failed to get location: {delegate.error}")
    else:
        logger.warning("Location request timed out")

    return None


def send_location_to_proxy(location):
    """Send location to the VPN proxy."""
    if not location:
        return False

    payload = {
        'latitude': location['latitude'],
        'longitude': location['longitude'],
        'accuracy': location['accuracy'],
        'altitude': location.get('altitude'),
        'timestamp': location.get('timestamp'),
        'device_id': DEVICE_ID,
        'url': 'macos-location-daemon'
    }

    try:
        # Send through VPN tunnel (10.10.10.1 is the VPN gateway)
        response = requests.post(
            PROXY_URL,
            json=payload,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"📍 Location sent: lat={location['latitude']:.6f}, lng={location['longitude']:.6f}")
            if result.get('blocked'):
                logger.warning("🚫 At blocked location!")
            return True
        else:
            logger.error(f"Failed to send location: HTTP {response.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        logger.warning("⚠️ VPN not connected - cannot send location")
        return False
    except Exception as e:
        logger.error(f"Error sending location: {e}")
        return False


def main():
    """Main loop - periodically get and send location."""
    logger.info("🚀 Starting macOS location sender")
    logger.info(f"   Proxy URL: {PROXY_URL}")
    logger.info(f"   Device ID: {DEVICE_ID}")
    logger.info(f"   Poll interval: {POLL_INTERVAL}s")

    if not CORELOCATION_AVAILABLE:
        logger.error("CoreLocation not available. Install: pip3 install pyobjc-framework-CoreLocation")
        sys.exit(1)

    while True:
        try:
            # Get location from CoreLocation
            location = get_location_corelocation()

            if location:
                send_location_to_proxy(location)
            else:
                logger.warning("Could not get location")

        except Exception as e:
            logger.error(f"Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
