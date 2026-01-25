#!/usr/bin/env python3
"""
MDM Location Polling Script

Polls SimpleMDM API for device locations and stores them in PostgreSQL.
Supports multiple devices - polls all enrolled devices and stores location per device ID.
Runs as a sidecar container in the mitmproxy pod.
"""

import os
import sys
import time
import logging
import requests
import psycopg2
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
SIMPLEMDM_API_KEY = os.environ.get('SIMPLEMDM_API_KEY', '2IkV3x1TEpS9r6AGtmeyvLlBMvwHzCeJgQY4O8VyTtoss2KR6qVpEZcQqPlmLrLV')
POLL_INTERVAL_SECONDS = int(os.environ.get('POLL_INTERVAL_SECONDS', '30'))

# Device IDs to poll (SimpleMDM device IDs)
# Can be overridden via environment variable as comma-separated list
DEFAULT_DEVICE_IDS = "2154382,2162127"  # iPhone, MacBook Air
DEVICE_IDS = os.environ.get('SIMPLEMDM_DEVICE_IDS', DEFAULT_DEVICE_IDS).split(',')

# Database configuration
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'postgres-service.hocuspocus.svc.cluster.local')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'mitmproxy')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'mitmproxy')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')


def get_device_location(device_id: str):
    """Fetch device location from SimpleMDM API."""
    url = f"https://a.simplemdm.com/api/v1/devices/{device_id}"

    try:
        response = requests.get(
            url,
            auth=(SIMPLEMDM_API_KEY, ''),
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        attrs = data.get('data', {}).get('attributes', {})
        device_name = attrs.get('device_name', device_id)

        lat = attrs.get('location_latitude')
        lng = attrs.get('location_longitude')
        accuracy = attrs.get('location_accuracy')
        updated_at = attrs.get('location_updated_at')

        if lat and lng:
            logger.info(f"📍 [{device_name}] Got location: lat={lat}, lng={lng}, accuracy={accuracy}m")
            return {
                'device_id': device_id,
                'device_name': device_name,
                'latitude': float(lat),
                'longitude': float(lng),
                'accuracy': accuracy,
                'location_updated_at': updated_at
            }
        else:
            logger.warning(f"⚠️ [{device_name}] Location not available from MDM")
            return None

    except requests.RequestException as e:
        logger.error(f"❌ Failed to fetch location for device {device_id}: {e}")
        return None


def request_location_update(device_id: str):
    """Request a fresh location update from the device."""
    url = f"https://a.simplemdm.com/api/v1/devices/{device_id}/lost_mode/update_location"

    try:
        response = requests.post(
            url,
            auth=(SIMPLEMDM_API_KEY, ''),
            timeout=10
        )
        if response.status_code == 202:
            logger.info(f"📍 Requested location update from device {device_id}")
            return True
        else:
            logger.warning(f"⚠️ Location update request for {device_id} returned {response.status_code}")
            return False
    except requests.RequestException as e:
        logger.error(f"❌ Failed to request location update for {device_id}: {e}")
        return False


def store_location(location):
    """Store location in PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()

        # Upsert location data
        cursor.execute("""
            INSERT INTO device_locations (device_id, device_name, latitude, longitude, accuracy, location_updated_at, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (device_id)
            DO UPDATE SET
                device_name = EXCLUDED.device_name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                accuracy = EXCLUDED.accuracy,
                location_updated_at = EXCLUDED.location_updated_at,
                fetched_at = EXCLUDED.fetched_at
        """, (
            location['device_id'],
            location.get('device_name', location['device_id']),
            location['latitude'],
            location['longitude'],
            location['accuracy'],
            location['location_updated_at'],
            datetime.utcnow()
        ))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"✅ Stored location for device {location['device_id']} ({location.get('device_name', 'unknown')})")
        return True

    except psycopg2.Error as e:
        logger.error(f"❌ Database error: {e}")
        return False


def ensure_table_exists():
    """Create device_locations table if it doesn't exist."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_locations (
                id SERIAL PRIMARY KEY,
                device_id VARCHAR(255) NOT NULL UNIQUE,
                device_name VARCHAR(255),
                latitude DECIMAL(10, 8) NOT NULL,
                longitude DECIMAL(11, 8) NOT NULL,
                accuracy INTEGER,
                location_updated_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_device_locations_device_id ON device_locations(device_id);
        """)

        # Add device_name column if it doesn't exist (migration for existing tables)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'device_locations' AND column_name = 'device_name'
                ) THEN
                    ALTER TABLE device_locations ADD COLUMN device_name VARCHAR(255);
                END IF;
            END $$;
        """)

        conn.commit()
        cursor.close()
        conn.close()

        logger.info("✅ Database table ready")
        return True

    except psycopg2.Error as e:
        logger.error(f"❌ Failed to create table: {e}")
        return False


def main():
    """Main polling loop."""
    logger.info(f"🚀 Starting MDM location polling for multiple devices")
    logger.info(f"   Device IDs: {', '.join(DEVICE_IDS)}")
    logger.info(f"   Poll interval: {POLL_INTERVAL_SECONDS}s")
    logger.info(f"   Database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

    # Ensure table exists
    if not ensure_table_exists():
        logger.error("Failed to initialize database, exiting")
        sys.exit(1)

    while True:
        try:
            # Poll location for each device
            for device_id in DEVICE_IDS:
                device_id = device_id.strip()
                if not device_id:
                    continue

                location = get_device_location(device_id)

                if location:
                    store_location(location)
                else:
                    # Request a location update if none available
                    request_location_update(device_id)

        except Exception as e:
            logger.error(f"❌ Error in polling loop: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
