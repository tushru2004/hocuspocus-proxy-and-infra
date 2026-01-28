"""Dependency injection container."""
from typing import Optional

from infrastructure.config import AppConfig
from adapters.repositories import (
    PostgresDomainRepository,
    PostgresYouTubeChannelRepository,
    PostgresLocationRepository
)
from adapters.external_services import YouTubeAPIClient
from adapters.presentation import HTMLBlockPageRenderer
from application.use_cases import (
    CheckDomainAccess,
    CheckYouTubeAccess,
    StoreLocation,
    VerifyLocationRestrictions
)


class DependencyContainer:
    """Dependency injection container for the application."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._instances = {}

    def get_domain_repository(self) -> PostgresDomainRepository:
        """Get domain repository instance."""
        if 'domain_repo' not in self._instances:
            self._instances['domain_repo'] = PostgresDomainRepository(
                self._config.database.connection_string
            )
        return self._instances['domain_repo']

    def get_youtube_channel_repository(self) -> PostgresYouTubeChannelRepository:
        """Get YouTube channel repository instance."""
        if 'youtube_repo' not in self._instances:
            self._instances['youtube_repo'] = PostgresYouTubeChannelRepository(
                self._config.database.connection_string
            )
        return self._instances['youtube_repo']

    def get_location_repository(self) -> PostgresLocationRepository:
        """Get location repository instance."""
        if 'location_repo' not in self._instances:
            self._instances['location_repo'] = PostgresLocationRepository(
                self._config.database.connection_string
            )
        return self._instances['location_repo']

    def get_youtube_api_client(self) -> YouTubeAPIClient:
        """Get YouTube API client instance."""
        if 'youtube_api' not in self._instances:
            self._instances['youtube_api'] = YouTubeAPIClient(
                self._config.youtube.api_key
            )
        return self._instances['youtube_api']

    def get_block_page_renderer(self) -> HTMLBlockPageRenderer:
        """Get block page renderer instance."""
        if 'block_page_renderer' not in self._instances:
            self._instances['block_page_renderer'] = HTMLBlockPageRenderer()
        return self._instances['block_page_renderer']

    def get_check_domain_access_use_case(self) -> CheckDomainAccess:
        """Get CheckDomainAccess use case instance."""
        if 'check_domain_access' not in self._instances:
            self._instances['check_domain_access'] = CheckDomainAccess(
                self.get_domain_repository()
            )
        return self._instances['check_domain_access']

    def get_check_youtube_access_use_case(self) -> CheckYouTubeAccess:
        """Get CheckYouTubeAccess use case instance."""
        if 'check_youtube_access' not in self._instances:
            self._instances['check_youtube_access'] = CheckYouTubeAccess(
                self.get_youtube_channel_repository(),
                self.get_youtube_api_client()
            )
        return self._instances['check_youtube_access']

    def get_store_location_use_case(self) -> StoreLocation:
        """Get StoreLocation use case instance."""
        if 'store_location' not in self._instances:
            self._instances['store_location'] = StoreLocation(
                self.get_location_repository()
            )
        return self._instances['store_location']

    def get_verify_location_restrictions_use_case(self) -> VerifyLocationRestrictions:
        """Get VerifyLocationRestrictions use case instance."""
        if 'verify_location' not in self._instances:
            self._instances['verify_location'] = VerifyLocationRestrictions(
                self.get_location_repository()
            )
        return self._instances['verify_location']
