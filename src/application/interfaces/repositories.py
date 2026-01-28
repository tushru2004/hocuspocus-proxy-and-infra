"""Repository interfaces (protocols) for the application layer."""
from typing import Protocol, List, Optional

from domain.entities import Domain, YouTubeChannel, Location, BlockedZone
from domain.value_objects import LocationData


class DomainRepository(Protocol):
    """Interface for domain repository."""

    def get_allowed_domains(self) -> List[Domain]:
        """Get all allowed domains."""
        ...


class YouTubeChannelRepository(Protocol):
    """Interface for YouTube channel repository."""

    def get_allowed_channels(self) -> List[YouTubeChannel]:
        """Get all allowed YouTube channels."""
        ...


class LocationRepository(Protocol):
    """Interface for location repository."""

    def store_location(self, location_data: LocationData) -> None:
        """Store location data."""
        ...

    def get_recent_locations(self, limit: int = 20) -> List[Location]:
        """Get recent locations."""
        ...

    def get_blocked_zones(self) -> List[BlockedZone]:
        """Get all blocked zones."""
        ...
