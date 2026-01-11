"""Domain exceptions for proxy handler."""


class DomainError(Exception):
    """Base exception for domain errors."""
    pass


class LocationTrackingError(DomainError):
    """Raised when location tracking fails."""
    pass


class DomainAccessDeniedError(DomainError):
    """Raised when access to a domain is denied."""

    def __init__(self, domain: str, reason: str):
        self.domain = domain
        self.reason = reason
        super().__init__(f"Access denied to {domain}: {reason}")


class YouTubeChannelBlockedError(DomainError):
    """Raised when a YouTube channel is blocked."""

    def __init__(self, video_id: str, channel_id: str):
        self.video_id = video_id
        self.channel_id = channel_id
        super().__init__(f"YouTube video {video_id} blocked (channel {channel_id} not whitelisted)")


class LocationBasedBlockError(DomainError):
    """Raised when browsing is blocked due to location."""

    def __init__(self, location_name: str, distance: float):
        self.location_name = location_name
        self.distance = distance
        super().__init__(f"Browsing blocked at {location_name} ({distance:.0f}m from blocked zone)")
