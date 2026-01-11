"""PostgreSQL implementation of domain repository."""
from typing import List
import logging
import psycopg
from psycopg.rows import dict_row

from domain.entities import Domain


class PostgresDomainRepository:
    """PostgreSQL implementation of DomainRepository."""

    def __init__(self, connection_string: str):
        self._connection_string = connection_string

    def get_allowed_domains(self) -> List[Domain]:
        """Get all allowed domains from database."""
        try:
            with psycopg.connect(self._connection_string, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT domain FROM allowed_hosts WHERE enabled = true")
                    rows = cursor.fetchall()
                    domains = [Domain(domain=row['domain'], enabled=True) for row in rows]
                    logging.info(f"✅ Loaded {len(domains)} allowed hosts from database")
                    return domains
        except Exception as e:
            logging.error(f"❌ Failed to load allowed hosts from database: {e}")
            # Return fallback
            return [Domain(domain="amazon.com", enabled=True)]
