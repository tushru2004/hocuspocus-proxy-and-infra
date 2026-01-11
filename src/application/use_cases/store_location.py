"""Use case for storing location data."""
import logging

from domain.value_objects import LocationData
from application.interfaces.repositories import LocationRepository


class StoreLocation:
    """Use case for storing location data in the database."""

    def __init__(self, location_repository: LocationRepository):
        self._location_repository = location_repository

    def execute(self, location_data: LocationData) -> None:
        """
        Store location data.

        Args:
            location_data: Location data to store
        """
        try:
            self._location_repository.store_location(location_data)
            logging.info(
                f"📍 Location stored: {location_data.coordinates.latitude}, "
                f"{location_data.coordinates.longitude} for {location_data.url}"
            )
        except Exception as e:
            logging.error(f"❌ Failed to store location: {e}")
            raise
