"""Use case for checking YouTube video access."""
from typing import List, Optional
import logging
from urllib.parse import urlparse, parse_qs

from domain.entities import YouTubeChannel
from domain.value_objects import AccessDecision, BlockReason
from application.interfaces.repositories import YouTubeChannelRepository
from application.interfaces.services import YouTubeAPIService


class CheckYouTubeAccess:
    """Use case for checking if a YouTube video is allowed."""

    def __init__(
        self,
        channel_repository: YouTubeChannelRepository,
        youtube_api_service: YouTubeAPIService
    ):
        self._channel_repository = channel_repository
        self._youtube_api_service = youtube_api_service
        self._video_to_channel_cache: dict[str, str] = {}

    def execute(self, url: str) -> AccessDecision:
        """
        Check if a YouTube video URL is allowed based on channel whitelist.

        Args:
            url: YouTube URL to check

        Returns:
            AccessDecision indicating if video is allowed
        """
        # Extract video ID
        video_id = self._extract_video_id(url)
        if not video_id:
            # Not a video URL, allow it
            return AccessDecision.allow(
                BlockReason.NOT_WHITELISTED,
                "Not a YouTube video URL"
            )

        # Get channel ID
        channel_id = self._get_channel_id(video_id)
        if not channel_id:
            logging.warning(f"⚠️  Could not determine channel for video {video_id}, BLOCKING by default")
            return AccessDecision.deny(
                BlockReason.YOUTUBE_CHANNEL_BLOCKED,
                f"Could not verify channel for video {video_id}"
            )

        # Check if channel is allowed
        allowed_channels = self._channel_repository.get_allowed_channels()
        allowed_channel_ids = [ch.channel_id for ch in allowed_channels]

        if channel_id in allowed_channel_ids:
            logging.info(f"✅ ALLOWING video {video_id} (channel {channel_id} is whitelisted)")
            return AccessDecision.allow(
                BlockReason.YOUTUBE_CHANNEL_BLOCKED,  # Using same reason for consistency
                f"YouTube channel {channel_id} is whitelisted"
            )
        else:
            logging.info(f"🚫 BLOCKING video {video_id} (channel {channel_id} not in whitelist)")
            return AccessDecision.deny(
                BlockReason.YOUTUBE_CHANNEL_BLOCKED,
                f"YouTube channel {channel_id} not whitelisted"
            )

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        try:
            logging.info(f"🔍 Extracting video ID from URL: {url}")
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            logging.info(f"  Path: {parsed.path}, Query: {parsed.query}")

            # Check for 'v' parameter (desktop/mobile watch page)
            if 'v' in query_params:
                video_id = query_params['v'][0]
                # Fix malformed video IDs (e.g., "LIhkYiYLON0?v=LIhkYiYLON0")
                if '?' in video_id:
                    video_id = video_id.split('?')[0]
                    logging.info(f"  🔧 Cleaned malformed video ID: {video_id}")
                logging.info(f"  ✅ Extracted video ID from 'v' param: {video_id}")
                return video_id

            # Check for 'docid' parameter (mobile API calls)
            if 'docid' in query_params:
                video_id = query_params['docid'][0]
                logging.info(f"  ✅ Extracted video ID from 'docid' param: {video_id}")
                return video_id

            # Check for youtu.be short URL
            if 'youtu.be/' in url:
                video_id = parsed.path.strip('/')
                logging.info(f"  ✅ Extracted video ID from youtu.be path: {video_id}")
                return video_id

            logging.warning(f"  ⚠️  Could not extract video ID from URL: {url}")
            return None
        except Exception as e:
            logging.error(f"Error extracting video ID from {url}: {e}")
            return None

    def _get_channel_id(self, video_id: str) -> Optional[str]:
        """Get channel ID from video ID, using cache."""
        # Check cache first
        if video_id in self._video_to_channel_cache:
            return self._video_to_channel_cache[video_id]

        # Call API
        channel_id = self._youtube_api_service.get_channel_id_from_video(video_id)
        if channel_id:
            self._video_to_channel_cache[video_id] = channel_id

        return channel_id

    @property
    def is_enabled(self) -> bool:
        """Check if YouTube filtering is enabled."""
        allowed_channels = self._channel_repository.get_allowed_channels()
        return len(allowed_channels) > 0
