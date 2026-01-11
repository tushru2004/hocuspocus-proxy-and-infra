"""Domain entities for proxy handler."""
from dataclasses import dataclass
from typing import Optional
from math import radians, sin, cos, sqrt, atan2

from .value_objects import GPSCoordinates


@dataclass
class BlockedZone:
    """A geographical zone where browsing is blocked."""
    coordinates: GPSCoordinates
    radius_meters: float
    name: str

    def is_within_zone(self, location: GPSCoordinates) -> tuple[bool, float]:
        """
        Check if a location is within this blocked zone.

        Returns:
            Tuple of (is_within_zone, distance_in_meters)
        """
        distance = self._calculate_distance(location)
        return (distance <= self.radius_meters, distance)

    def _calculate_distance(self, location: GPSCoordinates) -> float:
        """Calculate distance to location using Haversine formula."""
        R = 6371000  # Earth radius in meters

        lat1_rad = radians(self.coordinates.latitude)
        lat2_rad = radians(location.latitude)
        delta_lat = radians(location.latitude - self.coordinates.latitude)
        delta_lon = radians(location.longitude - self.coordinates.longitude)

        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c

        return distance


@dataclass
class Domain:
    """A domain with access rules."""
    domain: str
    enabled: bool = True

    def matches(self, host: str) -> bool:
        """Check if this domain matches the given host."""
        return self.domain in host


@dataclass
class YouTubeChannel:
    """A YouTube channel entity."""
    channel_id: str
    channel_name: str
    enabled: bool = True


@dataclass
class Location:
    """A recorded location data point."""
    id: Optional[int]
    device_id: str
    latitude: float
    longitude: float
    accuracy: Optional[float]
    altitude: Optional[float]
    url: Optional[str]
    timestamp: str
    received_at: Optional[str] = None

    @property
    def coordinates(self) -> GPSCoordinates:
        """Get GPS coordinates."""
        return GPSCoordinates(latitude=self.latitude, longitude=self.longitude)
