"""Use case for verifying location restrictions."""
from typing import List, Optional
import logging

from domain.entities import BlockedZone
from domain.value_objects import GPSCoordinates, AccessDecision, BlockReason
from domain.exceptions import LocationBasedBlockError


class VerifyLocationRestrictions:
    """Use case for checking if current location is in a blocked zone."""

    def __init__(self, blocked_zones: List[BlockedZone]):
        self._blocked_zones = blocked_zones
        self._currently_at_blocked_location = False
        self._current_blocked_zone: Optional[BlockedZone] = None
        self._last_distance: Optional[float] = None

    def execute(self, coordinates: GPSCoordinates) -> AccessDecision:
        """
        Check if browsing should be allowed at the given location.

        Args:
            coordinates: Current GPS coordinates

        Returns:
            AccessDecision indicating if browsing is allowed
        """
        for zone in self._blocked_zones:
            is_within, distance = zone.is_within_zone(coordinates)
            if is_within:
                self._currently_at_blocked_location = True
                self._current_blocked_zone = zone
                self._last_distance = distance

                logging.warning(
                    f"🚫 BLOCKING ENABLED - At blocked location ({zone.name}) - {distance:.0f}m away"
                )
                return AccessDecision.deny(
                    BlockReason.LOCATION_RESTRICTED,
                    f"At blocked location: {zone.name} ({distance:.0f}m from center)"
                )

        # Not at any blocked location
        self._currently_at_blocked_location = False
        self._current_blocked_zone = None
        self._last_distance = None

        logging.info("✅ Browsing allowed - Not at any blocked location")
        return AccessDecision.allow(
            BlockReason.LOCATION_RESTRICTED,  # Using same reason for consistency
            "Not at blocked location"
        )

    @property
    def is_blocked(self) -> bool:
        """Check if currently at a blocked location."""
        return self._currently_at_blocked_location

    @property
    def blocked_zone_name(self) -> Optional[str]:
        """Get name of current blocked zone, if any."""
        return self._current_blocked_zone.name if self._current_blocked_zone else None

    @property
    def blocked_zone_id(self) -> Optional[int]:
        """Get ID of current blocked zone, if any."""
        return self._current_blocked_zone.id if self._current_blocked_zone else None

    @property
    def has_blocked_zones(self) -> bool:
        """Check if any blocked zones are configured."""
        return len(self._blocked_zones) > 0
