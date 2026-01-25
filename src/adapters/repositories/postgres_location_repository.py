"""PostgreSQL implementation of location repository."""
from typing import List
import logging
import psycopg
from psycopg.rows import dict_row

from domain.entities import Location, BlockedZone
from domain.value_objects import LocationData, GPSCoordinates


class PostgresLocationRepository:
    """PostgreSQL implementation of LocationRepository."""

    def __init__(self, connection_string: str):
        self._connection_string = connection_string

    def store_location(self, location_data: LocationData) -> None:
        """Store location data in database."""
        try:
            with psycopg.connect(self._connection_string) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO locations
                           (device_id, latitude, longitude, accuracy, altitude, url, timestamp)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            location_data.device_id,
                            location_data.coordinates.latitude,
                            location_data.coordinates.longitude,
                            location_data.accuracy,
                            location_data.altitude,
                            location_data.url,
                            location_data.timestamp
                        )
                    )
                    conn.commit()
        except Exception as e:
            logging.error(f"❌ Failed to store location in database: {e}")
            raise

    def get_recent_locations(self, limit: int = 20) -> List[Location]:
        """Get recent locations from database."""
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """SELECT id, device_id, latitude, longitude, accuracy, altitude, url,
                                  timestamp, received_at
                           FROM locations
                           ORDER BY received_at DESC
                           LIMIT %s""",
                        (limit,)
                    )
                    rows = cursor.fetchall()
                    return [
                        Location(
                            id=row['id'],
                            device_id=row['device_id'],
                            latitude=row['latitude'],
                            longitude=row['longitude'],
                            accuracy=row['accuracy'],
                            altitude=row['altitude'],
                            url=row['url'],
                            timestamp=str(row['timestamp']),
                            received_at=str(row['received_at']) if row['received_at'] else None
                        )
                        for row in rows
                    ]
        except Exception as e:
            logging.error(f"❌ Failed to get locations from database: {e}")
            return []

    def get_blocked_zones(self) -> List[BlockedZone]:
        """Load blocked zones from database."""
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """SELECT id, name, latitude, longitude, radius_meters
                           FROM blocked_locations
                           WHERE enabled = true"""
                    )
                    rows = cursor.fetchall()
                    zones = [
                        BlockedZone(
                            id=row['id'],
                            coordinates=GPSCoordinates(
                                latitude=float(row['latitude']),
                                longitude=float(row['longitude'])
                            ),
                            radius_meters=float(row['radius_meters']),
                            name=row['name']
                        )
                        for row in rows
                    ]
                    logging.info(f"✅ Loaded {len(zones)} blocked zones from database")
                    return zones
        except Exception as e:
            logging.error(f"❌ Failed to load blocked zones from database: {e}")
            return []

    def get_location_whitelist(self, blocked_location_id: int) -> List[str]:
        """Get whitelisted domains for a specific blocked location."""
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """SELECT domain
                           FROM blocked_location_whitelist
                           WHERE blocked_location_id = %s AND enabled = true""",
                        (blocked_location_id,)
                    )
                    rows = cursor.fetchall()
                    domains = [row['domain'] for row in rows]
                    logging.info(f"✅ Loaded {len(domains)} whitelisted domains for blocked location {blocked_location_id}")
                    return domains
        except Exception as e:
            logging.error(f"❌ Failed to load location whitelist from database: {e}")
            return []

    def get_device_location(self, device_id: str = None) -> GPSCoordinates | None:
        """Get the latest device location from MDM polling table.

        Args:
            device_id: Optional device ID. If not provided, returns most recent location.

        Returns:
            GPSCoordinates if location found, None otherwise.
        """
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    if device_id:
                        cursor.execute(
                            """SELECT latitude, longitude, accuracy, location_updated_at, fetched_at
                               FROM device_locations
                               WHERE device_id = %s""",
                            (device_id,)
                        )
                    else:
                        # Get most recent location
                        cursor.execute(
                            """SELECT latitude, longitude, accuracy, location_updated_at, fetched_at
                               FROM device_locations
                               ORDER BY fetched_at DESC
                               LIMIT 1"""
                        )

                    row = cursor.fetchone()
                    if row and row['latitude'] and row['longitude']:
                        logging.info(
                            f"📍 Got device location from DB: lat={row['latitude']}, "
                            f"lng={row['longitude']}, fetched_at={row['fetched_at']}"
                        )
                        return GPSCoordinates(
                            latitude=float(row['latitude']),
                            longitude=float(row['longitude'])
                        )
                    else:
                        logging.warning("⚠️ No device location found in database")
                        return None
        except Exception as e:
            logging.error(f"❌ Failed to get device location from database: {e}")
            return None

    def has_fresh_location_data(self, max_age_seconds: int = 300, device_id: str = None) -> bool:
        """Check if device has fresh location data.

        Args:
            max_age_seconds: Maximum age of location data in seconds (default: 5 minutes)
            device_id: Optional specific device ID to check. If None, checks any device.

        Returns:
            True if the device (or any device) has location data newer than max_age_seconds
        """
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    if device_id:
                        cursor.execute(
                            """SELECT COUNT(*) as count
                               FROM device_locations
                               WHERE device_id = %s
                               AND fetched_at > NOW() - MAKE_INTERVAL(secs => %s)
                               AND latitude IS NOT NULL
                               AND longitude IS NOT NULL""",
                            (device_id, max_age_seconds)
                        )
                    else:
                        cursor.execute(
                            """SELECT COUNT(*) as count
                               FROM device_locations
                               WHERE fetched_at > NOW() - MAKE_INTERVAL(secs => %s)
                               AND latitude IS NOT NULL
                               AND longitude IS NOT NULL""",
                            (max_age_seconds,)
                        )
                    row = cursor.fetchone()
                    has_fresh = row and row['count'] > 0
                    device_info = f"device {device_id}" if device_id else "any device"
                    if has_fresh:
                        logging.info(f"✅ Fresh location data available for {device_info}")
                    else:
                        logging.warning(f"⚠️ No fresh location data for {device_info} (max age: {max_age_seconds}s)")
                    return has_fresh
        except Exception as e:
            logging.error(f"❌ Failed to check location freshness: {e}")
            return False

    def get_location_data_age_seconds(self) -> int | None:
        """Get the age of the most recent location data in seconds.

        Returns:
            Age in seconds, or None if no location data exists
        """
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """SELECT EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at))) as age_seconds
                           FROM device_locations
                           WHERE latitude IS NOT NULL AND longitude IS NOT NULL"""
                    )
                    row = cursor.fetchone()
                    if row and row['age_seconds'] is not None:
                        age = int(row['age_seconds'])
                        logging.info(f"📍 Location data age: {age} seconds")
                        return age
                    return None
        except Exception as e:
            logging.error(f"❌ Failed to get location data age: {e}")
            return None
