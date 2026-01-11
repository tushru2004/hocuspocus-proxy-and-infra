"""Configuration management."""
import os
from dataclasses import dataclass
from typing import List

from domain.entities import BlockedZone
from domain.value_objects import GPSCoordinates


@dataclass
class DatabaseConfig:
    """Database configuration."""
    host: str
    port: str
    database: str
    user: str
    password: str

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Load database config from environment variables."""
        return cls(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            database=os.getenv('POSTGRES_DB', 'mitmproxy'),
            user=os.getenv('POSTGRES_USER', 'mitmproxy'),
            password=os.getenv('POSTGRES_PASSWORD', 'mitmproxy')
        )


@dataclass
class YouTubeConfig:
    """YouTube API configuration."""
    api_key: str

    @classmethod
    def from_env(cls) -> 'YouTubeConfig':
        """Load YouTube config from environment variables."""
        return cls(api_key=os.getenv('YOUTUBE_API_KEY', ''))


@dataclass
class AppConfig:
    """Application configuration."""
    database: DatabaseConfig
    youtube: YouTubeConfig
    blocked_zones: List[BlockedZone]

    @classmethod
    def load(cls) -> 'AppConfig':
        """Load application configuration."""
        # Load blocked zones from constants
        blocked_zones = [
            BlockedZone(
                coordinates=GPSCoordinates(latitude=48.1785, longitude=16.4207),
                radius_meters=100,
                name='Mautner-Markhof-Gasse 11/11, Vienna, Austria, 1110'
            ),
            BlockedZone(
                coordinates=GPSCoordinates(latitude=48.20028, longitude=16.36116),
                radius_meters=100,
                name='Phil Cafe, Gumpendorfer Str. 10-12, 1060 Wien'
            )
        ]

        return cls(
            database=DatabaseConfig.from_env(),
            youtube=YouTubeConfig.from_env(),
            blocked_zones=blocked_zones
        )
