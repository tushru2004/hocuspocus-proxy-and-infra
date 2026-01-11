"""PostgreSQL implementation of location repository."""
from typing import List
import logging
import psycopg
from psycopg.rows import dict_row

from domain.entities import Location
from domain.value_objects import LocationData


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
