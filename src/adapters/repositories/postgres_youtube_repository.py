"""PostgreSQL implementation of YouTube channel repository."""
from typing import List
import logging
import psycopg
from psycopg.rows import dict_row

from domain.entities import YouTubeChannel


class PostgresYouTubeChannelRepository:
    """PostgreSQL implementation of YouTubeChannelRepository."""

    def __init__(self, connection_string: str):
        self._connection_string = connection_string

    def get_allowed_channels(self) -> List[YouTubeChannel]:
        """Get all allowed YouTube channels from database."""
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT channel_id, channel_name FROM youtube_channels WHERE enabled = true"
                    )
                    rows = cursor.fetchall()
                    channels = [
                        YouTubeChannel(
                            channel_id=row['channel_id'],
                            channel_name=row['channel_name'],
                            enabled=True
                        )
                        for row in rows
                    ]

                    if channels:
                        channel_names = [ch.channel_name for ch in channels]
                        logging.info(
                            f"✅ YouTube filtering ENABLED for {len(channels)} channels: {channel_names}"
                        )
                    else:
                        logging.info("ℹ️  YouTube filtering DISABLED (no channels configured)")

                    return channels
        except Exception as e:
            logging.error(f"❌ Failed to load YouTube channels from database: {e}")
            return []
