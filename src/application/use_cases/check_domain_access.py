"""Use case for checking domain access."""
from typing import List
import logging

from domain.entities import Domain
from domain.value_objects import AccessDecision, BlockReason
from application.interfaces.repositories import DomainRepository


class CheckDomainAccess:
    """Use case for checking if a domain should be allowed."""

    # Essential hosts that must always work
    ESSENTIAL_HOSTS = ["apple.com", "icloud.com", "icloud-content.com", "mzstatic.com"]

    # Captive portal detection hosts
    CAPTIVE_PORTAL_HOSTS = [
        "captive.apple.com",
        "connectivitycheck.gstatic.com",
        "clients3.google.com",
        "msftconnecttest.com",
        "detectportal.firefox.com",
        "nmcheck.gnome.org",
        "network-test.debian.org",
    ]

    def __init__(self, domain_repository: DomainRepository):
        self._domain_repository = domain_repository
        self._auto_whitelisted_hosts: set[str] = set()

    def execute(self, host: str, base_domain: str) -> AccessDecision:
        """
        Check if access to a domain should be allowed.

        Args:
            host: Full hostname (e.g., www.amazon.com)
            base_domain: Base domain (e.g., amazon.com)

        Returns:
            AccessDecision indicating if access is allowed
        """
        # 1. Check captive portal detection URLs
        if any(portal_host in host for portal_host in self.CAPTIVE_PORTAL_HOSTS):
            logging.info(f"✅ Allowing captive portal detection URL: {host}")
            return AccessDecision.allow(
                BlockReason.CAPTIVE_PORTAL,
                f"Captive portal detection URL: {host}"
            )

        # 2. Check auto-detected captive portals (excluding youtube.com)
        if base_domain in self._auto_whitelisted_hosts and base_domain != 'youtube.com':
            logging.info(f"✅ Allowing auto-detected captive portal: {base_domain}")
            return AccessDecision.allow(
                BlockReason.CAPTIVE_PORTAL,
                f"Auto-detected captive portal: {base_domain}"
            )

        # 3. Check essential hosts
        if base_domain in self.ESSENTIAL_HOSTS:
            logging.info(f"✅ Allowing essential host: {base_domain}")
            return AccessDecision.allow(
                BlockReason.ESSENTIAL_ALWAYS_ALLOWED,
                f"Essential host: {base_domain}"
            )

        # 4. Check whitelisted domains
        allowed_domains = self._domain_repository.get_allowed_domains()
        for domain in allowed_domains:
            # Check if domain matches either the host or the base_domain
            if domain.matches(host) or domain.matches(base_domain):
                logging.info(f"✅ Allowing whitelisted domain: {host} (matches {domain.domain})")
                return AccessDecision.allow(
                    BlockReason.NOT_WHITELISTED,  # Using this as "whitelisted" reason
                    f"Whitelisted domain: {host}"
                )

        # 5. Block everything else
        logging.info(f"🚫 BLOCKING non-whitelisted domain: {base_domain}")
        return AccessDecision.deny(
            BlockReason.NOT_WHITELISTED,
            f"Domain not whitelisted: {base_domain}"
        )

    def add_auto_whitelisted_host(self, domain: str) -> None:
        """Add a domain to auto-whitelist (for captive portals)."""
        self._auto_whitelisted_hosts.add(domain)
        logging.info(f"🌐 Auto-whitelisted captive portal: {domain}")
