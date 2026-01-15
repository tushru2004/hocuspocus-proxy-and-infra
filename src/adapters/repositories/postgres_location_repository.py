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
