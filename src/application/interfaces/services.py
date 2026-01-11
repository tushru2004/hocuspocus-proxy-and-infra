"""Service interfaces (protocols) for the application layer."""
from typing import Protocol, Optional


class YouTubeAPIService(Protocol):
    """Interface for YouTube API service."""

    def get_channel_id_from_video(self, video_id: str) -> Optional[str]:
        """Get channel ID from video ID."""
        ...


class BlockPageRenderer(Protocol):
    """Interface for block page rendering."""

    def render_location_block_page(self, location_name: str) -> str:
        """Render location-based block page."""
        ...

    def render_domain_block_page(self, domain: str) -> str:
        """Render domain block page."""
        ...
