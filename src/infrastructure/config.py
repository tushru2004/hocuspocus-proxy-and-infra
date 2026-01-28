"""Configuration management."""
import os
import logging
from dataclasses import dataclass


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

    @classmethod
    def load(cls) -> 'AppConfig':
        """Load application configuration."""
        return cls(
            database=DatabaseConfig.from_env(),
            youtube=YouTubeConfig.from_env()
        )
