"""YouTube API client implementation."""
from typing import Optional
import logging
import requests


class YouTubeAPIClient:
    """YouTube Data API client."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def get_channel_id_from_video(self, video_id: str) -> Optional[str]:
        """Get YouTube channel ID from video ID using YouTube Data API."""
        if not self._api_key:
            logging.warning("YouTube API key not configured, cannot verify channel")
            return None

        try:
            api_url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                'part': 'snippet',
                'id': video_id,
                'key': self._api_key
            }

            response = requests.get(api_url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if 'items' in data and len(data['items']) > 0:
                    channel_id = data['items'][0]['snippet']['channelId']
                    channel_title = data['items'][0]['snippet']['channelTitle']

                    logging.info(f"📺 Video {video_id} belongs to channel: {channel_title} ({channel_id})")
                    return channel_id
            else:
                logging.error(f"YouTube API error: {response.status_code}")

        except Exception as e:
            logging.error(f"Error calling YouTube API: {e}")

        return None
