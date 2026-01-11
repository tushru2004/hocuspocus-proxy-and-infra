"""Value objects for the domain layer."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class GPSCoordinates:
    """Immutable GPS coordinates."""
    latitude: float
    longitude: float

    def __post_init__(self):
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")


class BlockReason(Enum):
    """Reasons why access might be blocked."""
    NOT_WHITELISTED = "domain_not_whitelisted"
    YOUTUBE_CHANNEL_BLOCKED = "youtube_channel_not_whitelisted"
    LOCATION_RESTRICTED = "at_blocked_location"
    ESSENTIAL_ALWAYS_ALLOWED = "essential_host"
    CAPTIVE_PORTAL = "captive_portal_detection"


@dataclass(frozen=True)
class AccessDecision:
    """Decision on whether to allow access to a resource."""
    allowed: bool
    reason: BlockReason
    message: Optional[str] = None

    @classmethod
    def allow(cls, reason: BlockReason, message: Optional[str] = None) -> 'AccessDecision':
        """Create an allow decision."""
        return cls(allowed=True, reason=reason, message=message)

    @classmethod
    def deny(cls, reason: BlockReason, message: str) -> 'AccessDecision':
        """Create a deny decision."""
        return cls(allowed=False, reason=reason, message=message)


@dataclass(frozen=True)
class LocationData:
    """Location data with accuracy and metadata."""
    coordinates: GPSCoordinates
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    timestamp: Optional[str] = None
    url: Optional[str] = None
    device_id: str = 'iPhone'
